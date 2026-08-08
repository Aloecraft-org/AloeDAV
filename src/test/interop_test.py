"""
The client against the server, over a real socket.

Unit tests of either half can agree with each other and both be wrong about the
wire. This runs the actual `AloeDAVClient` -- requests, sockets, uvicorn -- over
the server, which is the strongest evidence available short of pointing Apple
Calendar at it. It is also how the namespace bug in `list_calendar_objects` was
found: that REPORT could never have returned anything, and no unit test on
either side could have shown it, because each half was self-consistent.
"""
import shutil
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone

import uvicorn

from aloedav.client import AloeDAVClient
from aloedav.model.m00_constant import CalendarComponents
from aloedav.model.serial_util import to_resource
from aloedav.server import create_app
from aloedav.server.auth import FileAuthenticator
from aloedav.storage.backends import open_store

NY = "America/New_York"

SERIES = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VTIMEZONE", "TZID:America/New_York", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:standup@x", "SUMMARY:Standup",
    f"DTSTART;TZID={NY}:20260302T090000",
    "RRULE:FREQ=WEEKLY;COUNT=4",
    f"EXDATE;TZID={NY}:20260316T090000",
    "X-VENDOR-THING:keep me", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@x",
    f"RECURRENCE-ID;TZID={NY}:20260309T090000",
    f"DTSTART;TZID={NY}:20260309T110000",
    "SUMMARY:Standup moved", "END:VEVENT",
    "END:VCALENDAR"])

JULY = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:july@x", "SUMMARY:Summer party",
    "DTSTART:20260714T180000Z", "END:VEVENT", "END:VCALENDAR"])

CARD = "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", "UID:ada@x",
                    "FN:Ada Lovelace", "N:Lovelace;Ada;;;",
                    "EMAIL;TYPE=WORK:ada@example.com", "END:VCARD"])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveServerTest(unittest.TestCase):
    """One server per class: starting uvicorn per test would dominate the run."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        cls.store = open_store(cls.root)
        authenticator = FileAuthenticator(cls.root + "/users.json", iterations=1000)
        authenticator.add_user("alice", "pw")

        cls.port = free_port()
        cls.server = uvicorn.Server(uvicorn.Config(
            create_app(cls.store, authenticator),
            host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        deadline = time.monotonic() + 10
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        cls.store.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.client = AloeDAVClient(f"http://127.0.0.1:{self.port}", "alice", "pw",
                                    allow_delete_collection=True)
        for info in self.store.list_collections("alice"):
            self.store.delete_collection("alice", info.collection_id)

    def calendar(self, collection_id="work"):
        self.client.create_calendar("Work", "a description", collection_id,
                                    CalendarComponents.VEVENT | CalendarComponents.VTODO)
        return collection_id


class TestCollectionLifecycle(LiveServerTest):

    def test_create_and_list_a_calendar(self):
        self.calendar()
        [info] = self.client.list_collections()
        self.assertEqual(info.collection_id, "work")
        self.assertEqual(info.displayname, "Work")

    def test_create_and_list_an_addressbook(self):
        self.client.create_addressbook("People", "contacts", "people")
        [info] = self.client.list_collections()
        self.assertEqual(info.collection_type.value, "addressbook")

    def test_component_set_survives_the_round_trip(self):
        self.calendar()
        [info] = self.client.list_collections()
        self.assertIn("VEVENT", str(info.component_set))
        self.assertIn("VTODO", str(info.component_set))

    def test_creating_an_existing_calendar_reports_false(self):
        self.calendar()
        self.assertFalse(self.client.create_calendar("Work", "", "work"))

    def test_fetch_collection_reports_a_ctag(self):
        self.calendar()
        self.assertTrue(self.client.fetch_collection("work").ctag)

    def test_delete_collection(self):
        self.calendar()
        self.assertTrue(self.client.delete_collection("work"))
        self.assertEqual(self.client.list_collections(), [])


class TestResourceRoundTrip(LiveServerTest):

    def test_a_resource_survives_the_round_trip_byte_for_byte(self):
        self.calendar()
        resource = to_resource(SERIES)
        self.client.upsert_object("work", resource)
        back = self.client.fetch_resource("work", "standup@x.ics")
        self.assertEqual(back.to_webdav_string(), resource.to_webdav_string())

    def test_the_series_stays_together_across_the_wire(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        back = self.client.fetch_resource("work", "standup@x.ics")
        self.assertEqual(len(back.components), 2)
        self.assertEqual(back.master.summary, "Standup")
        self.assertEqual(back.overrides[0].summary, "Standup moved")

    def test_the_timezone_reference_survives(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        back = self.client.fetch_resource("work", "standup@x.ics")
        self.assertEqual(back.master.dtstart.tzid, NY)
        self.assertEqual(back.master.dtstart.to_utc(),
                         datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc))

    def test_unmodelled_content_survives(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        body = self.client.fetch_resource("work", "standup@x.ics").to_webdav_string()
        for fragment in ("X-VENDOR-THING:keep me", "BEGIN:VTIMEZONE",
                         "CALSCALE:GREGORIAN", "EXDATE"):
            self.assertIn(fragment, body)

    def test_an_edit_does_not_destroy_the_series(self):
        # The whole reason the resource model exists, exercised end to end.
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        resource = self.client.fetch_resource("work", "standup@x.ics")
        resource.master.summary = "Daily standup"
        self.client.upsert_object("work", resource)

        back = self.client.fetch_resource("work", "standup@x.ics")
        self.assertEqual(len(back.components), 2)
        self.assertEqual(back.master.summary, "Daily standup")
        self.assertEqual(back.overrides[0].summary, "Standup moved")

    def test_delete_removes_it(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        self.assertTrue(self.client.delete_object("work", "standup@x.ics"))
        self.assertEqual(len(self.client.list_calendar_objects("work")), 0)

    def test_a_vcard_round_trips(self):
        self.client.create_addressbook("People", "", "people")
        self.client.upsert_object("people", to_resource(CARD))
        [card] = self.client.list_addressbook_objects("people")
        self.assertEqual(card.full_name, "Ada Lovelace")


class TestReports(LiveServerTest):

    def populate(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        self.client.upsert_object("work", to_resource(JULY))

    def test_listing_without_a_window_returns_everything(self):
        self.populate()
        self.assertEqual(len(self.client.list_calendar_objects("work")), 3)

    def test_time_range_selects_by_expanded_instances(self):
        # March holds only the recurring series, and it is selected on an
        # instance the RRULE generates rather than on its stored DTSTART.
        self.populate()
        found = self.client.list_calendar_objects(
            "work", datetime(2026, 3, 20, tzinfo=timezone.utc),
            datetime(2026, 4, 1, tzinfo=timezone.utc))
        self.assertEqual({item.uid for item in found}, {"standup@x"})

    def test_time_range_excludes_what_falls_outside(self):
        self.populate()
        found = self.client.list_calendar_objects(
            "work", datetime(2026, 7, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 1, tzinfo=timezone.utc))
        self.assertEqual({item.uid for item in found}, {"july@x"})

    def test_an_empty_window_returns_nothing(self):
        self.populate()
        self.assertEqual(self.client.list_calendar_objects(
            "work", datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2020, 2, 1, tzinfo=timezone.utc)), [])

    def test_sync_reports_an_addition(self):
        self.calendar()
        token = self.client.fetch_collection("work").synctoken
        self.client.upsert_object("work", to_resource(SERIES))
        result = self.client.sync_collection("work", token)
        self.assertEqual([entry["file_name"] for entry in result["updated"]],
                         ["standup@x.ics"])

    def test_sync_reports_a_deletion(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        token = self.client.fetch_collection("work").synctoken
        self.client.delete_object("work", "standup@x.ics")
        result = self.client.sync_collection("work", token)
        self.assertEqual([entry["file_name"] for entry in result["deleted"]],
                         ["standup@x.ics"])

    def test_sync_with_the_current_token_reports_nothing(self):
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        token = self.client.fetch_collection("work").synctoken
        result = self.client.sync_collection("work", token)
        self.assertEqual(result["updated"], [])
        self.assertEqual(result["deleted"], [])


class TestFailures(LiveServerTest):

    def test_bad_credentials_raise(self):
        from aloedav.exceptions import AuthenticationError
        bad = AloeDAVClient(f"http://127.0.0.1:{self.port}", "alice", "wrong")
        with self.assertRaises(AuthenticationError):
            bad.list_collections()

    def test_fetching_a_missing_resource_raises(self):
        from aloedav.exceptions import ResourceNotFound
        self.calendar()
        with self.assertRaises(ResourceNotFound):
            self.client.fetch_resource("work", "nope.ics")

    def test_a_stale_etag_is_refused(self):
        from aloedav.exceptions import PreconditionFailed
        self.calendar()
        self.client.upsert_object("work", to_resource(SERIES))
        with self.assertRaises(PreconditionFailed):
            self.client.upsert_object("work", to_resource(JULY),
                                      etag="definitely-not-current")


if __name__ == "__main__":
    unittest.main()
