"""
Browser view tests.

The view is read-only, so these check that it shows what the store holds
without misrepresenting it -- particularly that a moved instance is shown where
it moved to, an excluded instance is not shown at all, and calendar text
written by someone else's client cannot inject markup.
"""
import shutil
import tempfile
import unittest

from starlette.testclient import TestClient

from aloedav.collection import CollectionType
from aloedav.model.serial_util import to_resource
from aloedav.storage.file_store import FileStore
from aloedav.web import create_app

NY = "America/New_York"

SERIES = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:standup@x", "SUMMARY:Team standup",
    "LOCATION:Room B",
    f"DTSTART;TZID={NY}:20260302T090000",
    f"DTEND;TZID={NY}:20260302T093000",
    "RRULE:FREQ=WEEKLY;BYDAY=MO",
    f"EXDATE;TZID={NY}:20260316T090000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@x",
    f"RECURRENCE-ID;TZID={NY}:20260309T090000",
    f"DTSTART;TZID={NY}:20260309T110000",
    "SUMMARY:Standup moved", "END:VEVENT",
    "END:VCALENDAR"])

BIRTHDAY = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:bday@x", "SUMMARY:Ada's birthday",
    "DTSTART;VALUE=DATE:20260714", "RRULE:FREQ=YEARLY",
    "END:VEVENT", "END:VCALENDAR"])

CARD = "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", "UID:ada@x",
                    "FN:Ada Lovelace", "N:Lovelace;Ada;;;",
                    "EMAIL:ada@example.com", "END:VCARD"])


class WebTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = FileStore(self.root)
        self.store.create_collection("alice", "work", CollectionType.CALENDAR, "Work")
        self.store.create_collection("alice", "book", CollectionType.ADDRESSBOOK, "People")
        self.store.put_resource("alice", "work", to_resource(SERIES))
        self.store.put_resource("alice", "work", to_resource(BIRTHDAY))
        self.store.put_resource("alice", "book", to_resource(CARD))
        self.client = TestClient(create_app(self.store))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def agenda(self, start):
        response = self.client.get(f"/alice/work/?start={start}")
        self.assertEqual(response.status_code, 200)
        return response.text


class TestNavigation(WebTest):

    def test_index_lists_users(self):
        self.assertIn("alice", self.client.get("/").text)

    def test_user_page_lists_collections(self):
        body = self.client.get("/alice/").text
        self.assertIn("Work", body)
        self.assertIn("People", body)

    def test_collection_page_reports_its_type(self):
        self.assertIn("addressbook", self.client.get("/alice/").text)

    def test_missing_collection_is_a_404(self):
        self.assertEqual(self.client.get("/alice/nope/").status_code, 404)

    def test_missing_resource_is_a_404(self):
        self.assertEqual(self.client.get("/alice/work/nope.ics").status_code, 404)

    def test_traversal_attempt_does_not_leak(self):
        response = self.client.get("/alice/work/..%2F..%2Fcollection.json")
        self.assertIn(response.status_code, (400, 404, 500))
        self.assertNotIn("sync_log", response.text)


class TestAgenda(WebTest):

    def test_recurring_instances_are_shown(self):
        self.assertIn("Team standup", self.agenda("2026-03-02"))

    def test_moved_instance_is_shown_where_it_moved_to(self):
        body = self.agenda("2026-03-09")
        self.assertIn("Standup moved", body)
        self.assertIn("11:00", body)

    def test_excluded_instance_is_absent(self):
        import re
        # The EXDATE'd Monday has nothing at all, so it gets no day heading --
        # its absence is the assertion.
        blocks = re.split(r'<div class="day">', self.agenda("2026-03-09"))
        mondays = {b.split("<")[0] for b in blocks if b.startswith("Monday")}
        self.assertIn("Monday 23 March 2026", mondays)
        self.assertNotIn("Monday 16 March 2026", mondays)

    def test_zoned_times_name_their_zone(self):
        self.assertIn("New York", self.agenda("2026-03-02"))

    def test_all_day_event_is_marked_rather_than_shown_at_midnight(self):
        body = self.agenda("2026-07-10")
        self.assertIn("all day", body)
        self.assertNotIn("00:00", body)

    def test_empty_window_says_so(self):
        # Before the series begins. A later window is never empty: both rules
        # here are unbounded, so they still generate instances in 2030.
        self.assertIn("Nothing scheduled", self.agenda("2020-01-01"))
        self.assertIn("Team standup", self.agenda("2030-01-01"))
        self.assertIn("Ada", self.agenda("2030-07-10"))

    def test_window_navigation_links_are_present(self):
        body = self.agenda("2026-03-02")
        self.assertIn("start=2026-01-31", body)   # a 30-day window earlier
        self.assertIn("start=2026-04-01", body)   # the next window

    def test_malformed_start_falls_back_to_today(self):
        self.assertEqual(self.client.get("/alice/work/?start=nonsense").status_code, 200)


class TestResourceView(WebTest):

    def test_detail_shows_the_stored_bytes(self):
        body = self.client.get("/alice/work/standup@x.ics").text
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("RRULE:FREQ=WEEKLY", body)

    def test_raw_returns_the_calendar_itself(self):
        response = self.client.get("/alice/work/standup@x.ics?raw")
        self.assertIn("text/calendar", response.headers["content-type"])
        self.assertTrue(response.text.startswith("BEGIN:VCALENDAR"))

    def test_address_book_lists_contacts(self):
        body = self.client.get("/alice/book/").text
        self.assertIn("Ada Lovelace", body)
        self.assertIn("ada@example.com", body)


class TestEscaping(WebTest):

    def test_summary_cannot_inject_markup(self):
        # Calendar text is written by other people's clients, so it is
        # untrusted input like anything else arriving over the wire.
        hostile = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
            "BEGIN:VEVENT", "UID:xss@x",
            "SUMMARY:<script>alert(1)</script>",
            "DTSTART:20260302T090000Z", "END:VEVENT", "END:VCALENDAR"])
        self.store.put_resource("alice", "work", to_resource(hostile))
        body = self.agenda("2026-03-02")
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_displayname_cannot_inject_markup(self):
        self.store.create_collection("alice", "evil", CollectionType.CALENDAR,
                                     "<img src=x onerror=alert(1)>")
        body = self.client.get("/alice/").text
        self.assertNotIn("<img src=x", body)
        self.assertIn("&lt;img", body)


if __name__ == "__main__":
    unittest.main()
