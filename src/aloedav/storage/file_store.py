"""
A store that keeps each resource as a file on disk.

    <root>/<user>/<collection_id>/collection.json
    <root>/<user>/<collection_id>/<filename>.ics

This is the alternative backend, for people who want their data readable with
`ls`, `grep` and any text editor: when an agent and Apple Calendar disagree
about an event, you can read exactly what each of them wrote. It is also
trivially diffed and backed up by ordinary tools.

`AloeliteStore` is the default because it gives real transactional integrity
rather than the hand-rolled atomic writes below, one portable file, and
optional encryption. The layouts are identical, so moving between the two is a
straight copy -- see `python -m aloedav.web --help` for the migrate command.
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

from aloedav.model.m01_resource import Resource
from aloedav.model.serial_util import to_resource
from aloedav.storage import (AlreadyExists, CollectionInfo, CollectionNotFound,
                             EtagMismatch, ResourceNotFoundInStore, Store,
                             StorageError, SyncResult)
from aloedav.storage._shared import (METADATA_NAME, append_change, build_info,
                                     build_sync, check_segment, compute_etag,
                                     default_component_set, is_resource_name,
                                     new_metadata)


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


def _read_exact(path: Path) -> bytes:
    """
    Reads a file back byte-for-byte.

    Binary mode, not text: Path.read_text applies universal-newline
    translation, which turns the CRLF that RFC 5545 requires into LF. That
    silently changed the content, so an ETag computed from the file never
    matched the one computed when it was written and every conditional request
    failed. Reading bytes makes the mistake unavailable.
    """
    return path.read_bytes()


def _write_atomically(path: Path, body: bytes) -> None:
    """
    Writes via a temporary file and a rename.

    A partial write would leave an unparseable resource where a valid one used
    to be, which is exactly the kind of silent destruction this project exists
    to avoid.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(body)
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
        return self.root / check_segment(user, "user")

    def _collection_dir(self, user: str, collection_id: str) -> Path:
        return self._user_dir(user) / check_segment(collection_id, "collection id")

    def _require_collection(self, user: str, collection_id: str) -> Path:
        directory = self._collection_dir(user, collection_id)
        if not (directory / METADATA_NAME).exists():
            raise CollectionNotFound(f"no such collection: /{user}/{collection_id}")
        return directory

    # ---- metadata -----------------------------------------------------

    def _read_metadata(self, directory: Path) -> dict:
        try:
            return json.loads(_read_exact(directory / METADATA_NAME).decode("utf-8"))
        except FileNotFoundError:
            raise CollectionNotFound(f"no such collection: {directory}")
        except json.JSONDecodeError as error:
            raise StorageError(f"unreadable collection metadata at {directory}: {error}")

    def _write_metadata(self, directory: Path, metadata: dict) -> None:
        _write_atomically(directory / METADATA_NAME,
                          json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"))

    def _info(self, user: str, collection_id: str, directory: Path,
              metadata: dict) -> CollectionInfo:
        return build_info(user, collection_id, metadata,
                          sum(1 for _ in self._resource_files(directory)))

    def _resource_files(self, directory: Path):
        for path in sorted(directory.iterdir()):
            if path.is_file() and is_resource_name(path.name):
                yield path

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

        if component_set is None:
            component_set = default_component_set(collection_type)
        metadata = new_metadata(collection_type, displayname or collection_id,
                                description, component_set)
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
            resource = to_resource(body.decode("utf-8"), compute_etag(body))
        except Exception:
            # A file this parser cannot read is left on disk untouched and
            # omitted from listings. Deleting it, or letting one bad file break
            # the whole listing, would both be worse than skipping it.
            return None
        resource.stored_name = path.name
        return resource

    def get_resource(self, user: str, collection_id: str, filename: str) -> Resource:
        directory = self._require_collection(user, collection_id)
        path = directory / check_segment(filename, "filename")
        if not path.is_file():
            raise ResourceNotFoundInStore(f"no such resource: /{user}/{collection_id}/{filename}")
        resource = self._load(path)
        if resource is None:
            raise StorageError(f"unreadable resource: /{user}/{collection_id}/{filename}")
        return resource

    def put_resource(self, user, collection_id, resource, filename=None,
                     if_match=None, if_none_match=False) -> str:
        directory = self._require_collection(user, collection_id)
        name = check_segment(filename or resource.filename(), "filename")
        path = directory / name
        body = resource.to_webdav_string().encode("utf-8")
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
            append_change(metadata, name, False)
            self._write_metadata(directory, metadata)
        return etag

    def delete_resource(self, user, collection_id, filename, if_match=None) -> None:
        directory = self._require_collection(user, collection_id)
        name = check_segment(filename, "filename")
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
            append_change(metadata, name, True)
            self._write_metadata(directory, metadata)

    # ---- change tracking ----------------------------------------------

    def sync(self, user: str, collection_id: str, token: str = None) -> SyncResult:
        directory = self._require_collection(user, collection_id)
        return build_sync(self._read_metadata(directory), token,
                          [p.name for p in self._resource_files(directory)])
