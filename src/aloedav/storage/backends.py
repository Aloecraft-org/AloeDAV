"""
Choosing and moving between backends.

The default is Aloelite, and that is a deliberate default rather than a
preference the user is asked to hold. Someone standing up a calendar server is
not thinking about storage engines, and making them choose would be asking for
a decision they have no basis to make. They get transactional integrity, one
portable file and the option of encryption without having to know that is what
they are getting.

The filesystem backend stays a first-class alternative, one flag away, for the
case where being able to read the data with `ls` and `grep` matters more. Since
both write the same tree, `migrate` moves an existing store either direction
without anyone having to start over -- which is what makes "switch if you want
to" a real offer rather than advice to be given before it is useful.
"""
from pathlib import Path

from aloedav.storage import Store

FILE = "file"
ALOELITE = "aloelite"
DEFAULT_BACKEND = ALOELITE

BACKENDS = (ALOELITE, FILE)

# Where each backend puts things when the caller only gives a root.
DEFAULT_ROOT = "./data"
ALOELITE_FILENAME = "aloedav.sqlite"
FILE_DIRNAME = "collections"

# Records which backend is live after a migration. Without it, migrating to
# the filesystem and then starting normally would silently serve the old store
# again, because the source is deliberately left in place -- the worst kind of
# failure, since everything appears to work and the data is simply stale.
MARKER_NAME = "active-backend"


def open_store(root=DEFAULT_ROOT, backend: str = DEFAULT_BACKEND,
               pin: bytes = None) -> Store:
    """
    Opens the store under `root`.

    `root` is a directory in both cases: the Aloelite backend puts one file
    inside it, the filesystem backend a tree. Keeping the shapes alike means a
    caller can switch backend without also relearning what to point at.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    if backend == ALOELITE:
        from aloedav.storage.aloelite_store import AloeliteStore
        return AloeliteStore(root / ALOELITE_FILENAME, pin=pin)
    if backend == FILE:
        from aloedav.storage.file_store import FileStore
        if pin is not None:
            raise ValueError("the filesystem backend cannot encrypt; use the "
                             "default aloelite backend for that")
        return FileStore(root / FILE_DIRNAME)
    raise ValueError(f"unknown backend {backend!r}; expected one of {', '.join(BACKENDS)}")


def set_active_backend(root, backend: str) -> None:
    """Records the backend to use under `root` from now on."""
    Path(root).mkdir(parents=True, exist_ok=True)
    (Path(root) / MARKER_NAME).write_text(backend + "\n", encoding="utf-8")


def detect_backend(root=DEFAULT_ROOT) -> str | None:
    """
    Which backend `root` should be opened with, if it holds anything.

    A recorded choice wins over what happens to be on disk, because after a
    migration both are present and only one of them is current.
    """
    root = Path(root)
    marker = root / MARKER_NAME
    if marker.is_file():
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded in BACKENDS:
            return recorded
    if (root / ALOELITE_FILENAME).exists():
        return ALOELITE
    if (root / FILE_DIRNAME).is_dir() and any((root / FILE_DIRNAME).iterdir()):
        return FILE
    return None


def migrate(source: Store, target: Store, overwrite: bool = False) -> dict:
    """
    Copies every collection and resource from one store into another.

    Resources move as stored bytes, so nothing is reparsed or re-serialized on
    the way -- a migration that "cleaned up" its input would be exactly the
    silent rewriting this project exists to avoid. Sync tokens are deliberately
    not carried across: they identify positions in a log the target does not
    have, and a client presenting one afterwards must be told to resync rather
    than be answered from a log that means something else.
    """
    from aloedav.storage import AlreadyExists

    moved = {"users": 0, "collections": 0, "resources": 0, "skipped": 0}
    for user in source.users():
        moved["users"] += 1
        for info in source.list_collections(user):
            try:
                target.create_collection(
                    user, info.collection_id, info.collection_type,
                    info.displayname, info.description, info.component_set)
            except AlreadyExists:
                if not overwrite:
                    moved["skipped"] += 1
                    continue
            moved["collections"] += 1

            for resource in source.list_resources(user, info.collection_id):
                target.put_resource(user, info.collection_id, resource,
                                    filename=resource.stored_name)
                moved["resources"] += 1
    return moved
