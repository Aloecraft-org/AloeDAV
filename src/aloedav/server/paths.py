"""
The URL tree, and how it maps onto the store.

    /                            the service root
    /<user>/                     the principal, and its home set
    /<user>/<collection>/        a calendar or address book
    /<user>/<collection>/<file>  one resource

The principal and the home set are deliberately the same URL. RFC 4791 allows
it, Radicale does it, and every client tested against it copes -- while a
separate `/principals/<user>/` level buys nothing but another thing to get
wrong.

Path segments arrive percent-encoded from the wire and are decoded here. They
are *not* validated here: the store validates them, because it is the thing
with something to lose, and a check that lives next to the filesystem access it
protects cannot be bypassed by a new caller.
"""
from enum import StrEnum
from urllib.parse import quote, unquote


class Kind(StrEnum):
    ROOT = "root"
    PRINCIPAL = "principal"
    COLLECTION = "collection"
    RESOURCE = "resource"


class Target:
    """What a request URL refers to."""

    __slots__ = ("kind", "user", "collection", "resource", "trailing_slash")

    def __init__(self, kind, user=None, collection=None, resource=None,
                 trailing_slash=False):
        self.kind = kind
        self.user = user
        self.collection = collection
        self.resource = resource
        self.trailing_slash = trailing_slash

    @property
    def is_collection(self) -> bool:
        return self.kind in (Kind.ROOT, Kind.PRINCIPAL, Kind.COLLECTION)

    def __repr__(self) -> str:
        return (f"<Target {self.kind} user={self.user!r} "
                f"collection={self.collection!r} resource={self.resource!r}>")


def parse_path(path: str) -> Target:
    """Reads a request path into what it addresses."""
    trailing = path.endswith("/")
    segments = [unquote(segment) for segment in path.split("/") if segment]

    if not segments:
        return Target(Kind.ROOT, trailing_slash=True)
    if len(segments) == 1:
        return Target(Kind.PRINCIPAL, user=segments[0], trailing_slash=trailing)
    if len(segments) == 2:
        return Target(Kind.COLLECTION, user=segments[0], collection=segments[1],
                      trailing_slash=trailing)
    if len(segments) == 3:
        return Target(Kind.RESOURCE, user=segments[0], collection=segments[1],
                      resource=segments[2], trailing_slash=trailing)
    # Deeper than the tree goes. Reported as a resource so the handler answers
    # 404 rather than silently addressing something shallower.
    return Target(Kind.RESOURCE, user=segments[0], collection=segments[1],
                  resource="/".join(segments[2:]), trailing_slash=trailing)


def encode(*segments) -> str:
    """Builds a path, percent-encoding each segment."""
    return "/".join(quote(str(s), safe="") for s in segments if s not in (None, ""))


def root_path() -> str:
    return "/"


def principal_path(user: str) -> str:
    return f"/{encode(user)}/"


def collection_path(user: str, collection: str) -> str:
    return f"/{encode(user, collection)}/"


def resource_path(user: str, collection: str, resource: str) -> str:
    # A collection-shaped trailing slash would make a client treat the resource
    # as a container, so resource paths never carry one.
    return f"/{encode(user, collection, resource)}"
