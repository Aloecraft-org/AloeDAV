"""
A store that keeps everything inside one Aloelite volume.

Aloelite is a filesystem held in a single SQLite file, so the layout is the
same tree `FileStore` writes to disk:

    /<user>/<collection_id>/collection.json
    /<user>/<collection_id>/<filename>.ics

This is the default backend. Against a directory of files it gives real
transactional integrity instead of hand-rolled atomic writes, one portable file
to back up or move, and optional encryption. It gives up being readable with
`ls` and `grep`; `FileStore` remains available for that, and the two layouts
are identical so migrating either way is a straight copy.

Two things are worth knowing about how this is driven.

Every call is serialized through one lock and the connection is opened with
`check_same_thread=False`. That pairing is deliberate and is the arrangement
Aloelite documents: the engine adds no thread safety of its own, so a holder
that serializes may share the connection. AloeDAV needs it because the web
layer dispatches store calls into a threadpool, so they genuinely arrive on
different threads.

Aloelite's transaction boundary wraps a single Mount operation and does not
nest, so writing a resource and recording it in the sync log cannot be one
transaction. The log is therefore written *first*. A crash between the two then
leaves a change recorded for a resource that did not change: a client refetches
something it already had, which costs a round trip. The other order would leave
a real change unrecorded, and a client that never hears about it stays stale
until something unrelated disturbs the collection. Wasted work beats silent
staleness.
"""
import json
import threading
from typing import Optional

from aloelite import errors as aloe_errors
from aloelite.aloelite import Aloelite

from aloedav.collection import CollectionType
from aloedav.model.m01_resource import Resource
from aloedav.model.serial_util import to_resource
from aloedav.storage import (AlreadyExists, CollectionInfo, CollectionNotFound,
                             EtagMismatch, ResourceNotFoundInStore, Store,
                             StorageError, SyncResult)
from aloedav.storage._shared import (METADATA_NAME, append_change, build_info,
                                     build_sync, check_segment, compute_etag,
                                     default_component_set, is_resource_name,
                                     new_metadata)

DEFAULT_VOLUME = "aloedav"


class AloeliteStore(Store):

    def __init__(self, path, volume: str = DEFAULT_VOLUME, pin: bytes = None,
                 create: bool = True):
        """
        Opens (and by default creates) the volume backing this store.

        `pin` encrypts the volume. Encryption is decided once, at creation, so
        a pin passed to an existing unencrypted volume will not retrofit one.
        """
        self._lock = threading.RLock()
        self._fs = Aloelite(str(path), check_same_thread=False)
        try:
            self._mount = self._fs.mount(volume, pin=pin, create=create)
        except BaseException:
            self._fs.close()
            raise
        self._mount.__enter__()

    def close(self) -> None:
        with self._lock:
            try:
                self._mount.__exit__(None, None, None)
            finally:
                self._fs.close()

    def __enter__(self) -> "AloeliteStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- paths --------------------------------------------------------

    def _user_path(self, user: str) -> str:
        return f"/{check_segment(user, 'user')}"

    def _collection_path(self, user: str, collection_id: str) -> str:
        return f"{self._user_path(user)}/{check_segment(collection_id, 'collection id')}"

    def _children(self, path: str, node_type: str = None) -> list:
        try:
            entries = self._mount.list(path)
        except aloe_errors.NotFound:
            return []
        if node_type is None:
            return list(entries)
        return [e for e in entries if e.type.value == node_type]

    def _exists(self, path: str) -> bool:
        try:
            self._mount.stat(path)
            return True
        except aloe_errors.NotFound:
            return False

    # ---- metadata -----------------------------------------------------

    def _read_metadata(self, user: str, collection_id: str) -> dict:
        path = f"{self._collection_path(user, collection_id)}/{METADATA_NAME}"
        try:
            raw = self._mount.read_all(path)
        except aloe_errors.NotFound:
            raise CollectionNotFound(f"no such collection: /{user}/{collection_id}")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError(
                f"unreadable collection metadata at /{user}/{collection_id}: {error}")

    def _write_metadata(self, user: str, collection_id: str, metadata: dict) -> None:
        collection = self._collection_path(user, collection_id)
        self._mount.put(f"{collection}/{METADATA_NAME}",
                        json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"))
        # Mirrored into Aloelite's own metadata so the volume reads sensibly in
        # its manager and over a FUSE mount. The JSON record above stays
        # authoritative; this is a courtesy to other tools.
        try:
            self._mount.set_metadata(collection, {
                "displayname": str(metadata.get("displayname", "")),
                "collection_type": str(metadata.get("collection_type", "")),
                "application": "aloedav"})
        except Exception:
            # Presentation only. Never fail a write because a hint did not take.
            pass

    def _resource_names(self, user: str, collection_id: str) -> list[str]:
        return sorted(e.name for e in self._children(
            self._collection_path(user, collection_id), "entry")
            if is_resource_name(e.name))

    def _require_collection(self, user: str, collection_id: str) -> dict:
        return self._read_metadata(user, collection_id)

    # ---- collections --------------------------------------------------

    def users(self) -> list[str]:
        with self._lock:
            return sorted(e.name for e in self._children("/", "container")
                          if not e.name.startswith("."))

    def list_collections(self, user: str) -> list[CollectionInfo]:
        with self._lock:
            found = []
            for entry in self._children(self._user_path(user), "container"):
                try:
                    metadata = self._read_metadata(user, entry.name)
                except (CollectionNotFound, StorageError):
                    continue          # a container that is not one of ours
                found.append(build_info(user, entry.name, metadata,
                                        len(self._resource_names(user, entry.name))))
            return sorted(found, key=lambda info: info.collection_id)

    def get_collection(self, user: str, collection_id: str) -> CollectionInfo:
        with self._lock:
            metadata = self._require_collection(user, collection_id)
            return build_info(user, collection_id, metadata,
                              len(self._resource_names(user, collection_id)))

    def create_collection(self, user, collection_id, collection_type,
                          displayname="", description="", component_set=None) -> CollectionInfo:
        with self._lock:
            path = self._collection_path(user, collection_id)
            if self._exists(f"{path}/{METADATA_NAME}"):
                raise AlreadyExists(f"collection already exists: /{user}/{collection_id}")

            if component_set is None:
                component_set = default_component_set(collection_type)
            metadata = new_metadata(collection_type, displayname or collection_id,
                                    description, component_set)
            self._mount.mkdir(path, parents=True, exist_ok=True)
            self._write_metadata(user, collection_id, metadata)
            return build_info(user, collection_id, metadata, 0)

    def delete_collection(self, user: str, collection_id: str) -> None:
        with self._lock:
            self._require_collection(user, collection_id)
            self._mount.remove_recursive(self._collection_path(user, collection_id))

    # ---- resources ----------------------------------------------------

    def list_resources(self, user: str, collection_id: str) -> list[Resource]:
        with self._lock:
            self._require_collection(user, collection_id)
            resources = []
            for name in self._resource_names(user, collection_id):
                resource = self._load(user, collection_id, name)
                if resource is not None:
                    resources.append(resource)
            return resources

    def _load(self, user: str, collection_id: str, name: str) -> Optional[Resource]:
        path = f"{self._collection_path(user, collection_id)}/{name}"
        body = self._mount.read_all(path)
        try:
            resource = to_resource(body.decode("utf-8"), compute_etag(body))
        except Exception:
            # Content this parser cannot read is left exactly where it is and
            # omitted from listings. Deleting it, or letting one bad resource
            # break a whole listing, would both be worse than skipping it.
            return None
        resource.stored_name = name
        return resource

    def get_resource(self, user: str, collection_id: str, filename: str) -> Resource:
        with self._lock:
            self._require_collection(user, collection_id)
            name = check_segment(filename, "filename")
            if not self._exists(f"{self._collection_path(user, collection_id)}/{name}"):
                raise ResourceNotFoundInStore(
                    f"no such resource: /{user}/{collection_id}/{filename}")
            resource = self._load(user, collection_id, name)
            if resource is None:
                raise StorageError(
                    f"unreadable resource: /{user}/{collection_id}/{filename}")
            return resource

    def _stored_bytes(self, path: str) -> Optional[bytes]:
        try:
            return self._mount.read_all(path)
        except aloe_errors.NotFound:
            return None

    def put_resource(self, user, collection_id, resource, filename=None,
                     if_match=None, if_none_match=False) -> str:
        with self._lock:
            metadata = self._require_collection(user, collection_id)
            name = check_segment(filename or resource.filename(), "filename")
            path = f"{self._collection_path(user, collection_id)}/{name}"
            body = resource.to_webdav_string().encode("utf-8")
            etag = compute_etag(body)

            existing = self._stored_bytes(path)
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

            append_change(metadata, name, False)
            self._write_metadata(user, collection_id, metadata)
            self._mount.put(path, body)
            return etag

    def delete_resource(self, user, collection_id, filename, if_match=None) -> None:
        with self._lock:
            metadata = self._require_collection(user, collection_id)
            name = check_segment(filename, "filename")
            path = f"{self._collection_path(user, collection_id)}/{name}"

            existing = self._stored_bytes(path)
            if existing is None:
                raise ResourceNotFoundInStore(f"no such resource: {name}")
            if if_match is not None and compute_etag(existing) != if_match.strip('"'):
                raise EtagMismatch(f"etag mismatch for {name}")

            append_change(metadata, name, True)
            self._write_metadata(user, collection_id, metadata)
            self._mount.remove(path)

    # ---- change tracking ----------------------------------------------

    def sync(self, user: str, collection_id: str, token: str = None) -> SyncResult:
        with self._lock:
            metadata = self._require_collection(user, collection_id)
            return build_sync(metadata, token,
                              self._resource_names(user, collection_id))
