"""
Resource-level tests.

A CalDAV resource is a VCALENDAR that may hold several components sharing a
UID -- a recurring master plus one VEVENT per modified instance. These tests
pin the property that made the resource type necessary: editing one instance
of a series must not destroy the rest of it.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from aloedav.client import AloeDAVClient
from aloedav.model.serial_util import to_model, to_resource
from aloedav.model.m01_resource import VCalendarResource, VCardResource
from aloedav.model.m02_vevent import VEVENT
from aloedav.model.m02_vcard import VCARD
from aloedav import testdata

RECURRING_WITH_OVERRIDE = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VTIMEZONE", "TZID:America/New_York",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500",
    "DTSTART:20071104T020000", "END:STANDARD",
    "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:standup-1", "SUMMARY:Standup",
    "DTSTART:20260302T090000Z", "RRULE:FREQ=WEEKLY;BYDAY=MO",
    "EXDATE:20260316T090000Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup-1", "RECURRENCE-ID:20260309T090000Z",
    "SUMMARY:Standup (moved)", "DTSTART:20260309T110000Z", "END:VEVENT",
    "END:VCALENDAR",
])


class TestSeriesSurvival(unittest.TestCase):

    def test_master_and_override_are_one_resource(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        self.assertEqual(len(resource.components), 2)
        self.assertEqual(resource.filename(), "standup-1.ics")

    def test_master_and_overrides_are_distinguishable(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        self.assertEqual(resource.master.summary, "Standup")
        self.assertIsNone(resource.master.recurrence_id)
        self.assertEqual(len(resource.overrides), 1)
        self.assertEqual(resource.overrides[0].summary, "Standup (moved)")
        self.assertEqual(resource.overrides[0].recurrence_id,
                         datetime(2026, 3, 9, 9, 0, tzinfo=timezone.utc))

    def test_editing_the_master_keeps_the_override(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        resource.master.summary = "Daily standup"
        back = to_resource(resource.to_webdav_string())
        self.assertEqual(len(back.components), 2)
        self.assertEqual(back.master.summary, "Daily standup")
        self.assertEqual(back.overrides[0].summary, "Standup (moved)")

    def test_editing_an_override_keeps_the_master(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        resource.overrides[0].summary = "Standup (moved again)"
        back = to_resource(resource.to_webdav_string())
        self.assertEqual(len(back.components), 2)
        self.assertEqual(back.master.summary, "Standup")
        self.assertEqual(back.overrides[0].summary, "Standup (moved again)")

    def test_recurrence_rule_and_exdate_survive(self):
        out = to_resource(RECURRING_WITH_OVERRIDE).to_webdav_string()
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=MO", out)
        self.assertIn("EXDATE:20260316T090000Z", out)

    def test_timezone_and_calendar_properties_survive(self):
        out = to_resource(RECURRING_WITH_OVERRIDE).to_webdav_string()
        self.assertIn("BEGIN:VTIMEZONE", out)
        self.assertIn("TZID:America/New_York", out)
        self.assertIn("CALSCALE:GREGORIAN", out)
        # Calendar-level content appears once, not once per component.
        self.assertEqual(out.count("BEGIN:VTIMEZONE"), 1)
        self.assertEqual(out.count("CALSCALE:GREGORIAN"), 1)

    def test_override_for_finds_by_recurrence_id(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        found = resource.override_for(datetime(2026, 3, 9, 9, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(found)
        self.assertEqual(found.summary, "Standup (moved)")
        self.assertIsNone(resource.override_for(datetime(2030, 1, 1, tzinfo=timezone.utc)))

    def test_master_is_serialized_before_its_overrides(self):
        out = to_resource(RECURRING_WITH_OVERRIDE).to_webdav_string()
        first, second = out.split("BEGIN:VEVENT")[1:3]
        self.assertNotIn("RECURRENCE-ID", first, "master should come first")
        self.assertIn("RECURRENCE-ID", second)

    def test_serialization_is_idempotent(self):
        # A write that changes nothing must produce the same bytes, or every
        # no-op sync would look like an edit to the server.
        once = to_resource(RECURRING_WITH_OVERRIDE).to_webdav_string()
        self.assertEqual(once, to_resource(once).to_webdav_string())


class TestResourceShapes(unittest.TestCase):

    def test_vcard_resource_wraps_one_card(self):
        resource = to_resource(testdata.TEST_VCARD_SIMPLE)
        self.assertIsInstance(resource, VCardResource)
        self.assertEqual(resource.card.full_name, "Forrest Gump")
        self.assertTrue(resource.filename().endswith(".vcf"))
        self.assertIn("text/vcard", resource.content_type)

    def test_multi_uid_calendar_is_tolerated(self):
        # Non-conformant as a CalDAV resource (RFC 4791 4.1) but valid as an
        # .ics file, and a client has to read it rather than reject it.
        resource = to_resource(testdata.TEST_VCALENDAR_MIXED)
        self.assertEqual(len(resource.components), 2)
        uids = {c.uid for c in resource.components}
        self.assertEqual(len(uids), 2)
        back = to_resource(resource.to_webdav_string())
        self.assertEqual(len(back.components), 2)

    def test_resource_content_type_is_calendar(self):
        self.assertIn("text/calendar",
                      to_resource(RECURRING_WITH_OVERRIDE).content_type)

    def test_empty_resource_cannot_be_named(self):
        with self.assertRaises(ValueError):
            VCalendarResource(components=[]).filename()

    def test_etag_propagates_to_resource_and_components(self):
        resource = to_resource(RECURRING_WITH_OVERRIDE, etag="abc123")
        self.assertEqual(resource.etag, "abc123")
        self.assertTrue(all(c.etag == "abc123" for c in resource.components))


class TestBackwardCompatibility(unittest.TestCase):
    """to_model stays the flat component view so existing callers keep working."""

    def test_to_model_still_returns_components(self):
        items = to_model(RECURRING_WITH_OVERRIDE)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(isinstance(i, VEVENT) for i in items))

    def test_to_model_and_to_resource_agree_on_content(self):
        items = to_model(RECURRING_WITH_OVERRIDE)
        resource = to_resource(RECURRING_WITH_OVERRIDE)
        self.assertEqual([i.summary for i in items],
                         [c.summary for c in resource.components])

    def test_single_component_item_still_serializes_standalone(self):
        item = to_model(testdata.TEST_VEVENT_SIMPLE)[0]
        out = item.to_webdav_string()
        self.assertTrue(out.startswith("BEGIN:VCALENDAR"))
        self.assertEqual(out.count("BEGIN:VEVENT"), 1)


class TestClientResourceFetch(unittest.TestCase):

    def client_returning(self, body, etag='"e1"'):
        class R:
            status_code = 200
            text = body
            content = body.encode()
            headers = {"ETag": etag}
        client = AloeDAVClient("https://dav.example.com/", "u", "p")
        return client, lambda *a, **k: R()

    def test_fetch_resource_keeps_the_series_together(self):
        client, fake = self.client_returning(RECURRING_WITH_OVERRIDE)
        with patch("aloedav.client.requests.request", fake):
            resource = client.fetch_resource("cal1", "standup-1.ics")
        self.assertEqual(len(resource.components), 2)
        self.assertEqual(resource.etag, "e1")

    def test_upsert_accepts_a_resource(self):
        captured = {}

        def fake(method, url, **kw):
            captured.update(method=method, url=url, body=kw.get("data"),
                            headers=kw.get("headers"))
            class R:
                status_code = 204
                headers = {"ETag": '"e2"'}
                text = ""
            return R()

        resource = to_resource(RECURRING_WITH_OVERRIDE)
        client = AloeDAVClient("https://dav.example.com/", "u", "p")
        with patch("aloedav.client.requests.request", fake):
            client.upsert_object("cal1", resource)

        self.assertTrue(captured["url"].endswith("/standup-1.ics"))
        self.assertIn("text/calendar", captured["headers"]["Content-Type"])
        # Both components go up together -- this is the whole point.
        self.assertEqual(captured["body"].decode().count("BEGIN:VEVENT"), 2)


if __name__ == "__main__":
    unittest.main()
