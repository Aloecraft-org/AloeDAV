"""
Fidelity tests: what an agent must NOT destroy when it edits an object that
another client wrote.

The scenario throughout is read-modify-write -- parse something a real calendar
client produced, change one field, serialize it back -- and the assertion is
that nothing else moved.
"""
import unittest
from datetime import datetime, timezone

from aloedav.exceptions import ParseError
from aloedav.model.serial_util import to_model, webdav_data
from aloedav.model.m00_constant import RecurrenceFrequency

APPLE_EVENT = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Apple Inc.//macOS 14//EN",
    "CALSCALE:GREGORIAN",
    "BEGIN:VTIMEZONE",
    "TZID:America/New_York",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "DTSTART:20070311T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "DTSTART:20071104T020000",
    "END:STANDARD",
    "END:VTIMEZONE",
    "BEGIN:VEVENT",
    "UID:real-1",
    "SUMMARY:Team sync",
    "DTSTART:20260301T090000Z",
    "DTEND:20260301T100000Z",
    "CREATED:20260101T000000Z",
    "LAST-MODIFIED:20260102T000000Z",
    "GEO:37.386013;-122.082932",
    "RESOURCES:Projector",
    "CONTACT:Jane",
    "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC",
    "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;WKST=SU",
    "END:VEVENT",
    "END:VCALENDAR",
])


class TestUnmodelledComponents(unittest.TestCase):

    def test_vtimezone_does_not_raise(self):
        # This raised AssertionError before unmodelled components were captured,
        # which made every non-UTC event from a mainstream client unreadable.
        items = to_model(APPLE_EVENT)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].summary, "Team sync")

    def test_vtimezone_survives_read_modify_write(self):
        event = to_model(APPLE_EVENT)[0]
        event.summary = "Team sync (edited)"
        out = event.to_webdav_string()
        for marker in ("BEGIN:VTIMEZONE", "TZID:America/New_York",
                       "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0500",
                       "BEGIN:STANDARD", "TZOFFSETTO:-0500", "END:VTIMEZONE"):
            self.assertIn(marker, out, f"{marker} lost")
        self.assertIn("Team sync (edited)", out)

    def test_nested_unknown_components_keep_their_structure(self):
        event = to_model(APPLE_EVENT)[0]
        out = event.to_webdav_string()
        # Balanced, and the timezone's own RRULE is not confused with the event's.
        self.assertEqual(out.count("BEGIN:VTIMEZONE"), 1)
        self.assertEqual(out.count("END:VTIMEZONE"), 1)
        self.assertEqual(out.count("BEGIN:DAYLIGHT"), 1)
        self.assertEqual(out.count("BEGIN:STANDARD"), 1)
        self.assertIn("RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", out)

    def test_calendar_level_property_survives(self):
        event = to_model(APPLE_EVENT)[0]
        self.assertIn("CALSCALE:GREGORIAN", event.to_webdav_string())

    def test_unknown_component_reparses(self):
        # The preserved block must itself be valid enough to parse again.
        once = to_model(APPLE_EVENT)[0].to_webdav_string()
        twice = to_model(once)[0].to_webdav_string()
        self.assertEqual(once.count("BEGIN:VTIMEZONE"), twice.count("BEGIN:VTIMEZONE"))
        self.assertIn("TZID:America/New_York", twice)


class TestUnmodelledProperties(unittest.TestCase):

    PRESERVED = ("CREATED:20260101T000000Z", "LAST-MODIFIED:20260102T000000Z",
                 "GEO:37.386013;-122.082932", "RESOURCES:Projector", "CONTACT:Jane")

    def test_unknown_properties_survive(self):
        event = to_model(APPLE_EVENT)[0]
        event.summary = "changed"
        out = event.to_webdav_string()
        for line in self.PRESERVED:
            self.assertIn(line, out, f"{line} lost")

    def test_unknown_properties_are_not_double_escaped(self):
        # They are stored verbatim, so a second round trip must not accumulate
        # backslashes the way a parse/escape cycle would.
        once = to_model(APPLE_EVENT)[0].to_webdav_string()
        twice = to_model(once)[0].to_webdav_string()
        for line in self.PRESERVED:
            self.assertIn(line, twice, f"{line} corrupted on the second pass")

    def test_x_properties_still_round_trip(self):
        event = to_model(APPLE_EVENT)[0]
        self.assertEqual(event.extended_attributes.get("X-APPLE-TRAVEL-ADVISORY-BEHAVIOR"),
                         "AUTOMATIC")
        self.assertIn("X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC",
                      event.to_webdav_string())

    def test_preserved_lines_do_not_leak_between_components(self):
        two = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "BEGIN:VEVENT", "UID:a", "SUMMARY:A", "DTSTART:20260301T090000Z",
            "GEO:1;2", "END:VEVENT",
            "BEGIN:VTODO", "UID:b", "SUMMARY:B", "RESOURCES:Room", "END:VTODO",
            "END:VCALENDAR",
        ])
        event, todo = to_model(two)
        self.assertIn("GEO:1;2", event.to_webdav_string())
        self.assertNotIn("RESOURCES:Room", event.to_webdav_string())
        self.assertIn("RESOURCES:Room", todo.to_webdav_string())
        self.assertNotIn("GEO:1;2", todo.to_webdav_string())


class TestRecurrenceRuleFidelity(unittest.TestCase):
    """
    A partially-modelled RRULE is worse than an unmodelled one: dropping BYDAY
    changes when the event recurs rather than merely losing detail.
    """

    RULES = [
        "FREQ=WEEKLY;BYDAY=MO,WE;WKST=SU",
        "FREQ=MONTHLY;INTERVAL=2;BYDAY=-1FR;BYSETPOS=-1",
        "FREQ=YEARLY;COUNT=5;BYMONTH=3;BYMONTHDAY=15",
        "FREQ=DAILY;UNTIL=20260401T000000Z",
        "FREQ=HOURLY;BYHOUR=9,10,11;BYMINUTE=0;BYSECOND=0",
        "FREQ=YEARLY;BYWEEKNO=20;BYYEARDAY=100",
        "FREQ=MINUTELY;INTERVAL=30",
        "FREQ=SECONDLY",
        "FREQ=WEEKLY;BYDAY=TU;X-VENDOR-THING=42",
    ]

    def event_with(self, rule):
        return "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:r",
            "SUMMARY:s", "DTSTART:20260302T090000Z", f"RRULE:{rule}",
            "END:VEVENT", "END:VCALENDAR",
        ])

    def rule_of(self, ics):
        line = next(l for l in ics.split("\r\n") if l.startswith("RRULE:"))
        return set(line[len("RRULE:"):].split(";"))

    def test_every_rrule_part_round_trips(self):
        for rule in self.RULES:
            with self.subTest(rule=rule):
                back = to_model(self.event_with(rule))[0].to_webdav_string()
                self.assertEqual(self.rule_of(back), set(rule.split(";")))

    def test_all_seven_frequencies_parse(self):
        for freq in RecurrenceFrequency:
            with self.subTest(freq=freq.value):
                item = to_model(self.event_with(f"FREQ={freq.value}"))[0]
                self.assertEqual(item.recurrence_rule.frequency, freq)

    def test_unknown_rrule_part_is_kept(self):
        item = to_model(self.event_with("FREQ=WEEKLY;X-VENDOR-THING=42"))[0]
        self.assertEqual(item.recurrence_rule.unknown_parts, ["X-VENDOR-THING=42"])

    def test_default_interval_is_not_emitted(self):
        back = to_model(self.event_with("FREQ=WEEKLY"))[0].to_webdav_string()
        self.assertEqual(self.rule_of(back), {"FREQ=WEEKLY"})


class TestStructuralErrors(unittest.TestCase):
    """
    Structure violations must raise a real exception. Assertions are stripped
    under `python -O`, which would turn a detected error into silent corruption.
    """

    def test_mismatched_end_raises_parse_error(self):
        with self.assertRaises(ParseError):
            webdav_data("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCARD")

    def test_component_in_wrong_parent_raises(self):
        with self.assertRaises(ParseError):
            webdav_data("BEGIN:VCARD\r\nVERSION:3.0\r\nBEGIN:VEVENT\r\n"
                        "UID:x\r\nEND:VEVENT\r\nEND:VCARD")

    def test_unclosed_component_raises(self):
        with self.assertRaises(ParseError):
            webdav_data("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:x")

    def test_unclosed_unknown_component_raises(self):
        with self.assertRaises(ParseError):
            webdav_data("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
                        "BEGIN:VTIMEZONE\r\nTZID:X\r\nEND:VCALENDAR")

    def test_errors_are_not_assertions(self):
        # Guards the -O failure mode: a bare `assert` would surface as
        # AssertionError, which ParseError deliberately is not.
        try:
            webdav_data("BEGIN:VCALENDAR\r\nEND:VCARD")
        except ParseError as exc:
            self.assertNotIsInstance(exc, AssertionError)
        else:
            self.fail("expected ParseError")


if __name__ == "__main__":
    unittest.main()
