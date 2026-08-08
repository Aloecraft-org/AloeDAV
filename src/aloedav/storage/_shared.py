"""
Semantics every backend must share.

The backends differ in where bytes live and nothing else. ETag derivation,
sync-log bookkeeping, the collection metadata shape and segment validation all
live here so the two implementations cannot quietly drift apart -- which is
what would make the shared contract tests meaningless.
"""
import hashlib
import os
from typing import Optional

from aloedav.collection import CollectionType, ComponentSet
from aloedav.storage import (CollectionInfo, StorageError, SyncChange,
                             SyncResult, SyncTokenExpired)

# The collection's own record, stored beside its resources under this name in
# every backend, so the layouts match and migration is a straight copy.
METADATA_NAME = "collection.json"

# How many changes the sync log keeps. Beyond this the oldest entries are
# dropped and clients holding those tokens are told to resync; an unbounded log
# would grow forever on a long-lived server.
SYNC_LOG_LIMIT = 2000


def compute_etag(body: bytes) -> str:
    """
    A strong validator derived from the content.

    Hashing rather than assigning a random id means an unchanged rewrite keeps
    its ETag, so a client re-uploading identical bytes is not told the resource
    changed, and validators survive a restart.

    Takes bytes, not str: the ETag must be over exactly what was stored, and
    going through str invites the encoding and newline translation that already
    broke this once.
    """
    return hashlib.sha256(body).hexdigest()[:32]


def check_segment(value: str, what: str) -> str:
    """
    Validates one path segment.

    A server takes these straight from a request URL, so this is a security
    boundary rather than tidiness. It rejects what is dangerous -- separators,
    traversal, NUL, dotfiles -- rather than allowing only a known-good
    character set, because real UIDs contain all sorts of punctuation and an
    allowlist would refuse legitimate resources.
    """
    text = str(value or "")
    if (not text
            or text in (".", "..")
            or text.startswith(".")
            or "/" in text or "\\" in text or "\0" in text
            or text == METADATA_NAME):        # would clobber the metadata record
        raise StorageError(f"unsafe {what}: {value!r}")
    return text


def is_resource_name(name: str) -> bool:
    """Whether a stored name is a resource rather than bookkeeping."""
    return bool(name) and name != METADATA_NAME and not name.startswith(".")


def default_component_set(collection_type: CollectionType) -> ComponentSet:
    if CollectionType(collection_type) is CollectionType.ADDRESSBOOK:
        return ComponentSet.VCONTACT
    return ComponentSet.VEVENT | ComponentSet.VTODO | ComponentSet.VJOURNAL


def new_metadata(collection_type, displayname, description, component_set) -> dict:
    metadata = {"collection_type": CollectionType(collection_type).value,
                "displayname": displayname,
                "description": description or "",
                "component_set": component_set.value,
                "sync_log": []}
    append_change(metadata, None, False)
    return metadata


def append_change(metadata: dict, filename: Optional[str], deleted: bool) -> str:
    """Records one change and returns the new sync token."""
    log = metadata.setdefault("sync_log", [])
    ordinal = (log[-1]["ordinal"] + 1) if log else 1
    token = f"{ordinal:08d}-{os.urandom(8).hex()}"
    log.append({"ordinal": ordinal, "token": token,
                "filename": filename, "deleted": deleted})
    if len(log) > SYNC_LOG_LIMIT:
        del log[:-SYNC_LOG_LIMIT]
    return token


def current_token(metadata: dict) -> str:
    log = metadata.get("sync_log", [])
    return log[-1]["token"] if log else ""


def build_info(user: str, collection_id: str, metadata: dict,
               resource_count: int) -> CollectionInfo:
    token = current_token(metadata)
    return CollectionInfo(
        user=user,
        collection_id=collection_id,
        collection_type=CollectionType(metadata["collection_type"]),
        displayname=metadata.get("displayname", ""),
        description=metadata.get("description", ""),
        component_set=ComponentSet(metadata.get("component_set", 0)),
        ctag=token,
        sync_token=token,
        resource_count=resource_count)


def build_sync(metadata: dict, token: Optional[str],
               present: list[str]) -> SyncResult:
    """
    Resolves a sync request against the log.

    With no token the answer is the whole collection. With a token older than
    the retained log the caller is told to resync rather than handed a partial
    answer, which is what RFC 6578 3.2 requires -- a client that silently
    misses a change stays wrong until something else disturbs it.
    """
    log = metadata.get("sync_log", [])
    now = current_token(metadata)

    if not token:
        return SyncResult(changes=[SyncChange(filename=name) for name in sorted(present)],
                          sync_token=now, is_initial=True)

    position = next((entry["ordinal"] for entry in log if entry["token"] == token), None)
    if position is None:
        raise SyncTokenExpired(f"sync token no longer held: {token}")

    # Later entries win, so a file changed several times is reported once with
    # its final state.
    latest = {}
    for entry in log:
        if entry["ordinal"] > position and entry["filename"]:
            latest[entry["filename"]] = entry["deleted"]
    return SyncResult(
        changes=[SyncChange(filename=name, deleted=deleted)
                 for name, deleted in sorted(latest.items())],
        sync_token=now)
