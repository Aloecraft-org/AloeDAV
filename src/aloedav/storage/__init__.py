"""
Persistence for a server.

This is deliberately not `aloedav.collection`. That package is the *client*
abstraction -- a handle on a collection you are talking to, local or remote.
A server needs a different shape: several users, durable state, addressing by
resource rather than by component, and sync tokens that can legitimately expire.
Conflating the two would make both worse.

The unit throughout is the `Resource`, never the component. A recurring master
and its RECURRENCE-ID overrides share one UID and therefore one filename, so a
store keyed by component silently drops whichever arrives second -- the same
defect the model layer had before `m01_resource`, and far more damaging here,
because storage is the server's actual memory.
"""
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from aloedav.collection import CollectionType, ComponentSet
from aloedav.exceptions import AloeDAVClientError
from aloedav.model.m01_resource import Resource


class StorageError(AloeDAVClientError):
    """Something went wrong reaching the store."""


class CollectionNotFound(StorageError):
    pass


class ResourceNotFoundInStore(StorageError):
    pass


class EtagMismatch(StorageError):
    """The caller's If-Match did not name the version now stored."""


class AlreadyExists(StorageError):
    pass


class SyncTokenExpired(StorageError):
    """
    The caller's sync token predates what the log still holds.

    RFC 6578 3.2 requires answering this with a 403 carrying
    DAV:valid-sync-token so the client knows to start a full resync, rather
    than a partial answer that would leave it quietly out of date.
    """


class CollectionInfo(BaseModel):
    """A collection's metadata, without its contents."""

    user: str
    collection_id: str
    collection_type: CollectionType
    displayname: str = ""
    description: str = ""
    component_set: ComponentSet = ComponentSet.INVALID

    # Changes whenever anything in the collection changes, so a client can skip
    # a full listing. Both are served from the same underlying counter.
    ctag: str = ""
    sync_token: str = ""
    resource_count: int = 0

    @property
    def path(self) -> str:
        return f"/{self.user}/{self.collection_id}"


class SyncChange(BaseModel):
    filename: str
    deleted: bool = False


class SyncResult(BaseModel):
    changes: list[SyncChange] = Field(default_factory=list)
    sync_token: str = ""
    # True when the caller passed no token, so the answer is the whole
    # collection rather than a delta.
    is_initial: bool = False


class Store(ABC):
    """Everything a server needs to read and write persisted state."""

    # ---- collections --------------------------------------------------

    @abstractmethod
    def users(self) -> list[str]:
        """Every user with at least one collection."""

    @abstractmethod
    def list_collections(self, user: str) -> list[CollectionInfo]:
        ...

    @abstractmethod
    def get_collection(self, user: str, collection_id: str) -> CollectionInfo:
        ...

    @abstractmethod
    def create_collection(self, user: str, collection_id: str,
                          collection_type: CollectionType, displayname: str = "",
                          description: str = "",
                          component_set: ComponentSet = None) -> CollectionInfo:
        ...

    @abstractmethod
    def delete_collection(self, user: str, collection_id: str) -> None:
        ...

    # ---- resources ----------------------------------------------------

    @abstractmethod
    def list_resources(self, user: str, collection_id: str) -> list[Resource]:
        ...

    @abstractmethod
    def get_resource(self, user: str, collection_id: str, filename: str) -> Resource:
        ...

    @abstractmethod
    def put_resource(self, user: str, collection_id: str, resource: Resource,
                     filename: str = None, if_match: str = None,
                     if_none_match: bool = False) -> str:
        """
        Writes a resource whole and returns its new ETag.

        `if_match` makes the write conditional on the stored version;
        `if_none_match` makes it conditional on there being no stored version,
        which is how a client says "create, do not overwrite".
        """

    @abstractmethod
    def delete_resource(self, user: str, collection_id: str, filename: str,
                        if_match: str = None) -> None:
        ...

    # ---- change tracking ----------------------------------------------

    @abstractmethod
    def sync(self, user: str, collection_id: str, token: str = None) -> SyncResult:
        """
        What changed since `token`. With no token, reports the whole collection.

        Raises SyncTokenExpired when the token is older than the retained log.
        """
