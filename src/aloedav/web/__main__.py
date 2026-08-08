"""
Runs the browser view:

    python -m aloedav.web --root ./data
    python -m aloedav.web --root ./data --demo    # seed sample data first

`--demo` writes a small calendar and address book into the store so there is
something to look at, including a recurring meeting with a moved instance
across a DST boundary -- the case the model work exists to get right.
"""
import argparse

import uvicorn

from aloedav.storage.file_store import FileStore
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

    try:
        store.create_collection("demo", "work", CollectionType.CALENDAR,
                                "Work calendar", "Sample data")
        store.create_collection("demo", "contacts", CollectionType.ADDRESSBOOK,
                                "Contacts", "Sample data")
    except AlreadyExists:
        pass

    for body in (DEMO_CALENDAR, DEMO_BIRTHDAY, DEMO_FLOATING):
        store.put_resource("demo", "work", to_resource(body))
    store.put_resource("demo", "contacts", to_resource(DEMO_CARD))


def main():
    parser = argparse.ArgumentParser(description="AloeDAV browser view")
    parser.add_argument("--root", default="./data", help="storage directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--demo", action="store_true", help="seed sample data")
    args = parser.parse_args()

    store = FileStore(args.root)
    if args.demo:
        seed(store)
        print(f"seeded sample data in {args.root}")

    uvicorn.run(create_app(store), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
