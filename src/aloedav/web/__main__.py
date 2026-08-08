"""
Runs the browser view, and moves data between storage backends.

    python -m aloedav.web --root ./data --demo      # serve, seeding sample data
    python -m aloedav.web migrate --to file         # switch to plain folders

Storage defaults to Aloelite: one portable file, real transactions, optional
encryption. Pass `--backend file` to keep each resource as a plain `.ics` you
can read with `ls` and `grep` instead, and `migrate` to move existing data
between the two in either direction.
"""
import argparse
import sys

import uvicorn

from aloedav.storage.backends import (ALOELITE, BACKENDS, DEFAULT_BACKEND,
                                      DEFAULT_ROOT, FILE, detect_backend,
                                      migrate, open_store, set_active_backend)
from aloedav.web import create_app


DEMO_CALENDAR = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AloeDAV//demo//EN",
    "BEGIN:VTIMEZONE", "TZID:America/New_York", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:standup@demo", "SUMMARY:Team standup",
    "LOCATION:Conference room B",
    "DTSTART;TZID=America/New_York:20260302T090000",
    "DTEND;TZID=America/New_York:20260302T093000",
    "RRULE:FREQ=WEEKLY;BYDAY=MO",
    "EXDATE;TZID=America/New_York:20260316T090000",
    "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@demo",
    "RECURRENCE-ID;TZID=America/New_York:20260309T090000",
    "DTSTART;TZID=America/New_York:20260309T110000",
    "DTEND;TZID=America/New_York:20260309T113000",
    "SUMMARY:Team standup (moved to 11)", "END:VEVENT",
    "END:VCALENDAR"])

DEMO_BIRTHDAY = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AloeDAV//demo//EN",
    "BEGIN:VEVENT", "UID:birthday@demo", "SUMMARY:Ada's birthday",
    "DTSTART;VALUE=DATE:20260714", "DTEND;VALUE=DATE:20260715",
    "RRULE:FREQ=YEARLY", "END:VEVENT", "END:VCALENDAR"])

DEMO_FLOATING = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AloeDAV//demo//EN",
    "BEGIN:VEVENT", "UID:journal@demo", "SUMMARY:Write morning pages",
    "DTSTART:20260303T070000", "DURATION:PT30M",
    "RRULE:FREQ=DAILY;COUNT=20", "END:VEVENT", "END:VCALENDAR"])

DEMO_CARD = "\r\n".join([
    "BEGIN:VCARD", "VERSION:3.0", "UID:ada@demo", "FN:Ada Lovelace",
    "N:Lovelace;Ada;;;", "EMAIL;TYPE=WORK:ada@example.com",
    "TEL;TYPE=CELL:+1-555-0100", "END:VCARD"])


def seed(store):
    from aloedav.collection import CollectionType
    from aloedav.model.serial_util import to_resource
    from aloedav.storage import AlreadyExists

    for collection_id, kind, name in [("work", CollectionType.CALENDAR, "Work calendar"),
                                      ("contacts", CollectionType.ADDRESSBOOK, "Contacts")]:
        try:
            store.create_collection("demo", collection_id, kind, name, "Sample data")
        except AlreadyExists:
            pass

    for body in (DEMO_CALENDAR, DEMO_BIRTHDAY, DEMO_FLOATING):
        store.put_resource("demo", "work", to_resource(body))
    store.put_resource("demo", "contacts", to_resource(DEMO_CARD))


def _add_storage_arguments(parser):
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help=f"storage directory (default: {DEFAULT_ROOT})")
    parser.add_argument("--backend", choices=BACKENDS, default=None,
                        help=f"storage backend (default: {DEFAULT_BACKEND}, or "
                             "whichever already holds data under --root)")


def _resolve_backend(args) -> str:
    """
    Uses whatever is already there, so a user who migrated once does not have
    to keep passing the flag afterwards.
    """
    if args.backend:
        return args.backend
    return detect_backend(args.root) or DEFAULT_BACKEND


def run_serve(args) -> int:
    backend = _resolve_backend(args)
    store = open_store(args.root, backend)
    if args.demo:
        seed(store)
        print(f"seeded sample data in {args.root}")
    print(f"storage: {backend} under {args.root}")
    uvicorn.run(create_app(store), host=args.host, port=args.port)
    return 0


def run_migrate(args) -> int:
    source_backend = args.source or detect_backend(args.root)
    if source_backend is None:
        print(f"nothing to migrate: no store found under {args.root}", file=sys.stderr)
        return 1
    if source_backend == args.target:
        print(f"already using the {args.target} backend", file=sys.stderr)
        return 1

    source = open_store(args.root, source_backend)
    target = open_store(args.root, args.target)
    try:
        moved = migrate(source, target, overwrite=args.overwrite)
    finally:
        for store in (source, target):
            close = getattr(store, "close", None)
            if close:
                close()

    # Record the choice before reporting success, so a later plain run opens
    # what was just migrated into rather than the source left beside it.
    set_active_backend(args.root, args.target)

    print(f"migrated {source_backend} -> {args.target}: "
          f"{moved['collections']} collections, {moved['resources']} resources"
          + (f", {moved['skipped']} already present and skipped" if moved["skipped"] else ""))
    print(f"the {source_backend} store was left in place; remove it once you have "
          "checked the migration")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="aloedav.web", description="AloeDAV browser view and storage tools")
    _add_storage_arguments(parser)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--demo", action="store_true", help="seed sample data")

    subcommands = parser.add_subparsers(dest="command")
    mover = subcommands.add_parser(
        "migrate", help="move data between storage backends")
    _add_storage_arguments(mover)
    mover.add_argument("--to", dest="target", choices=BACKENDS, required=True,
                       help="backend to migrate into")
    mover.add_argument("--from", dest="source", choices=BACKENDS, default=None,
                       help="backend to migrate out of (default: whichever holds data)")
    mover.add_argument("--overwrite", action="store_true",
                       help="write into collections that already exist in the target")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return run_migrate(args)
    return run_serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
