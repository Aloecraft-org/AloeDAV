"""
A store that keeps each resource as a file on disk.

    <root>/<user>/<collection_id>/collection.json
    <root>/<user>/<collection_id>/<filename>.ics

Chosen over a database because the project's first principle is not destroying
what it does not understand, and a layout you can `cat` makes that checkable
rather than merely asserted: when an agent and Apple Calendar disagree about an
event, you can read exactly what each of them wrote. It is also trivially
backed up and diffed by ordinary tools.

The cost is that a directory listing has to parse every file to answer a
listing, and that concurrent writers need real locking. Both are handled below
but neither is free, which is why `Store` is an interface -- a SQLite
implementation can drop in unchanged if the tradeoff stops paying.
"""
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from aloedav.collection import CollectionType, ComponentSet
from aloedav.model.m01_resource import Resource
from aloedav.model.serial_util import to_resource
from aloedav.storage import (AlreadyExists, CollectionInfo, CollectionNotFound,
                             EtagMismatch, ResourceNotFoundInStore, Store,
                             StorageError, SyncChange, SyncResult,
                             SyncTokenExpired)

METADATA_NAME = "collection.json"

# How many changes the sync log keeps. Beyond this the oldest entries are
# dropped and clients holding those tokens are told to resync -- an unbounded
# log would grow forever on a long-lived server, which is the failure the
# in-memory LocalCollection has today.
SYNC_LOG_LIMIT = 2000

def _check_segment(value: str, what: str) -> str:
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
            or text == METADATA_NAME):        # would clobber the metadata file
        raise StorageError(f"unsafe {what}: {value!r}")
    return text


def compute_etag(body: str) -> str:
    """
    A strong validator derived from the content.

    Hashing rather than assigning a random id means an unchanged rewrite keeps
    its ETag, so a client that re-uploads identical bytes is not told the
    resource changed, and validators survive a restart.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


@contextmanager
def _locked(path: Path):
    """Exclusive lock over one collection, so concurrent writers serialize."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _read_exact(path: Path) -> str:
    """
    Reads a file back byte-for-byte.

    Path.read_text applies universal-newline translation, which turns the CRLF
    that RFC 5545 requires into LF. That silently changes the content, so an
    ETag computed from the file never matched the one computed when it was
    written and every conditional request failed.
    """
    with open(path, "r", encoding="utf-8", newline="") as stream:
        return stream.read()


def _write_atomically(path: Path, text: str) -> None:
    """
    Writes via a temporary file and a rename.

    A partial write would leave an unparseable resource where a valid one used
    to be, which is exactly the kind of silent destruction this project exists
    to avoid.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class FileStore(Store):

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- paths --------------------------------------------------------

    def _user_dir(self, user: str) -> Path:
        return self.root / _check_segment(user, "user")

    def _collection_dir(self, user: str, collection_id: str) -> Path:
        return self._user_dir(user) / _check_segment(collection_id, "collection id")

    def _require_collection(self, user: str, collection_id: str) -> Path:
        directory = self._collection_dir(user, collection_id)
        if not (directory / METADATA_NAME).exists():
            raise CollectionNotFound(f"no such collection: /{user}/{collection_id}")
        return directory

    # ---- metadata -----------------------------------------------------

    def _read_metadata(self, directory: Path) -> dict:
        try:
            return json.loads(_read_exact(directory / METADATA_NAME))
        except FileNotFoundError:
            raise CollectionNotFound(f"no such collection: {directory}")
        except json.JSONDecodeError as error:
            raise StorageError(f"unreadable collection metadata at {directory}: {error}")

    def _write_metadata(self, directory: Path, metadata: dict) -> None:
        _write_atomically(directory / METADATA_NAME,
                          json.dumps(metadata, indent=2, sort_keys=True))

    def _info(self, user: str, collection_id: str, directory: Path,
              metadata: dict) -> CollectionInfo:
        log = metadata.get("sync_log", [])
        token = log[-1]["token"] if log else ""
        return CollectionInfo(
            user=user,
            collection_id=collection_id,
            collection_type=CollectionType(metadata["collection_type"]),
            displayname=metadata.get("displayname", ""),
            description=metadata.get("description", ""),
            component_set=ComponentSet(metadata.get("component_set", 0)),
            ctag=token,
            sync_token=token,
            resource_count=sum(1 for _ in self._resource_files(directory)))

    def _resource_files(self, directory: Path):
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name != METADATA_NAME and not path.name.startswith("."):
                yield path

    def _append_change(self, metadata: dict, filename: Optional[str],
                       deleted: bool) -> str:
        log = metadata.setdefault("sync_log", [])
        ordinal = (log[-1]["ordinal"] + 1) if log else 1
        token = f"{ordinal:08d}-{os.urandom(8).hex()}"
        log.append({"ordinal": ordinal, "token": token,
                    "filename": filename, "deleted": deleted})
        if len(log) > SYNC_LOG_LIMIT:
            del log[:-SYNC_LOG_LIMIT]
        return token

    # ---- collections --------------------------------------------------

    def users(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and not p.name.startswith("."))

    def list_collections(self, user: str) -> list[CollectionInfo]:
        directory = self._user_dir(user)
        if not directory.exists():
            return []
        found = []
        for child in sorted(directory.iterdir()):
            if child.is_dir() and (child / METADATA_NAME).exists():
                found.append(self._info(user, child.name, child, self._read_metadata(child)))
        return found

    def get_collection(self, user: str, collection_id: str) -> CollectionInfo:
        directory = self._require_collection(user, collection_id)
        return self._info(user, collection_id, directory, self._read_metadata(directory))

    def create_collection(self, user, collection_id, collection_type,
                          displayname="", description="", component_set=None) -> CollectionInfo:
        directory = self._collection_dir(user, collection_id)
        if (directory / METADATA_NAME).exists():
            raise AlreadyExists(f"collection already exists: /{user}/{collection_id}")

        collection_type = CollectionType(collection_type)
        if component_set is None:
            component_set = (ComponentSet.VCONTACT
                             if collection_type is CollectionType.ADDRESSBOOK
                             else ComponentSet.VEVENT | ComponentSet.VTODO | ComponentSet.VJOURNAL)

        metadata = {"collection_type": collection_type.value,
                    "displayname": displayname or collection_id,
                    "description": description,
                    "component_set": component_set.value,
                    "sync_log": []}
        self._append_change(metadata, None, False)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_metadata(directory, metadata)
        return self._info(user, collection_id, directory, metadata)

    def delete_collection(self, user: str, collection_id: str) -> None:
        directory = self._require_collection(user, collection_id)
        shutil.rmtree(directory)

    # ---- resources ----------------------------------------------------

    def list_resources(self, user: str, collection_id: str) -> list[Resource]:
        directory = self._require_collection(user, collection_id)
        resources = []
        for path in self._resource_files(directory):
            resource = self._load(path)
            if resource is not None:
                resources.append(resource)
        return resources

    def _load(self, path: Path) -> Optional[Resource]:
        body = _read_exact(path)
        try:
            resource = to_resource(body, compute_etag(body))
        except Exception:
            # A file this parser cannot read is left on disk untouched and
            # omitted from listings. Deleting it, or letting one bad file break
            # the whole listing, would both be worse than skipping it.
            return None
        resource.stored_name = path.name
        return resource

    def get_resource(self, user: str, collection_id: str, filename: str) -> Resource:
        directory = self._require_collection(user, collection_id)
        path = directory / _check_segment(filename, "filename")
        if not path.is_file():
            raise ResourceNotFoundInStore(f"no such resource: /{user}/{collection_id}/{filename}")
        resource = self._load(path)
        if resource is None:
            raise StorageError(f"unreadable resource: /{user}/{collection_id}/{filename}")
        return resource

    def put_resource(self, user, collection_id, resource, filename=None,
                     if_match=None, if_none_match=False) -> str:
        directory = self._require_collection(user, collection_id)
        name = _check_segment(filename or resource.filename(), "filename")
        path = directory / name
        body = resource.to_webdav_string()
        etag = compute_etag(body)

        with _locked(directory / ".lock"):
            existing = _read_exact(path) if path.is_file() else None
            if if_none_match and existing is not None:
                raise AlreadyExists(f"resource already exists: {name}")
            if if_match is not None:
                if existing is None:
                    raise ResourceNotFoundInStore(f"no such resource: {name}")
                if compute_etag(existing) != if_match.strip('"'):
                    raise EtagMismatch(f"etag mismatch for {name}")

            # An identical body is not a change: recording one would hand every
            # syncing client a pointless round of work.
            if existing is not None and compute_etag(existing) == etag:
                return etag

            _write_atomically(path, body)
            metadata = self._read_metadata(directory)
            self._append_change(metadata, name, False)
            self._write_metadata(directory, metadata)
        return etag

    def delete_resource(self, user, collection_id, filename, if_match=None) -> None:
        directory = self._require_collection(user, collection_id)
        name = _check_segment(filename, "filename")
        path = directory / name

        with _locked(directory / ".lock"):
            if not path.is_file():
                raise ResourceNotFoundInStore(f"no such resource: {name}")
            if if_match is not None:
                stored = compute_etag(_read_exact(path))
                if stored != if_match.strip('"'):
                    raise EtagMismatch(f"etag mismatch for {name}")
            path.unlink()
            metadata = self._read_metadata(directory)
            self._append_change(metadata, name, True)
            self._write_metadata(directory, metadata)

    # ---- change tracking ----------------------------------------------

    def sync(self, user: str, collection_id: str, token: str = None) -> SyncResult:
        directory = self._require_collection(user, collection_id)
        metadata = self._read_metadata(directory)
        log = metadata.get("sync_log", [])
        current = log[-1]["token"] if log else ""

        if not token:
            return SyncResult(
                changes=[SyncChange(filename=p.name) for p in self._resource_files(directory)],
                sync_token=current, is_initial=True)

        position = next((entry["ordinal"] for entry in log if entry["token"] == token), None)
        if position is None:
            raise SyncTokenExpired(f"sync token no longer held: {token}")

        # Later entries win, so a file changed several times is reported once
        # with its final state.
        latest = {}
        for entry in log:
            if entry["ordinal"] > position and entry["filename"]:
                latest[entry["filename"]] = entry["deleted"]
        return SyncResult(
            changes=[SyncChange(filename=name, deleted=deleted)
                     for name, deleted in sorted(latest.items())],
            sync_token=current)
