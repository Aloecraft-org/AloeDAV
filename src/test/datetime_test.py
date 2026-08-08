"""
Date-time representation tests.

The properties pinned here are the ones a bare `datetime` could not hold: which
of the four RFC 5545 forms a value is, and which zone a zoned value names.
Getting these wrong moves appointments on the user's calendar silently, so the
tests lean on cases where the failure would be invisible -- a DST boundary, an
all-day date, a TZID this machine cannot resolve.
"""
import unittest
from datetime import date, datetime, timedelta, timezone

from aloedav.model.m00_datetime import DateTimeValue, DateTimeKind
from aloedav.model.m01_base import RecurrenceRule
from aloedav.model.m02_vevent import VEVENT
from aloedav.model.serial_util import to_resource, to_model

NY = "America/New_York"


def wrap(*lines):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
                        "BEGIN:VEVENT", "UID:e1", "SUMMARY:s", *lines,
                        "END:VEVENT", "END:VCALENDAR"])


def reparse(event):
    return to_model(event.to_webdav_string())[0]


class TestTheFourForms(unittest.TestCase):

    def test_utc_value(self):
        v = DateTimeValue.parse("20260301T090000Z")
        self.assertIs(v.kind, DateTimeKind.UTC)
        self.assertIsNone(v.tzid)
        self.assertEqual(v.to_utc(), datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc))

    def test_floating_value(self):
        v = DateTimeValue.parse("20260301T090000")
        self.assertIs(v.kind, DateTimeKind.FLOATING)
        # A floating time names no instant -- that is the point of it.
        self.assertIsNone(v.to_utc())

    def test_date_value(self):
        v = DateTimeValue.parse("20260301", {"VALUE": "DATE"})
        self.assertIs(v.kind, DateTimeKind.DATE)
        self.assertEqual(v.date(), date(2026, 3, 1))
        self.assertIsNone(v.to_utc())

    def test_bare_eight_digits_is_a_date_without_the_parameter(self):
        self.assertIs(DateTimeValue.parse("20260301").kind, DateTimeKind.DATE)

    def test_zoned_value(self):
        v = DateTimeValue.parse("20260301T090000", {"TZID": NY})
        self.assertIs(v.kind, DateTimeKind.ZONED)
        self.assertEqual(v.tzid, NY)
        self.assertEqual(v.value, datetime(2026, 3, 1, 9, 0))

    def test_all_day_is_not_midnight(self):
        # The distinction a bare datetime cannot make: both are 00:00 naive.
        all_day = DateTimeValue.parse("20260301", {"VALUE": "DATE"})
        midnight = DateTimeValue.parse("20260301T000000")
        self.assertNotEqual(all_day, midnight)
        self.assertEqual(all_day.to_wire(), "20260301")
        self.assertEqual(midnight.to_wire(), "20260301T000000")

    def test_utc_designator_beats_a_stray_tzid(self):
        # RFC 5545 3.3.5 forbids TZID on a UTC value; some clients send both.
        v = DateTimeValue.parse("20260301T090000Z", {"TZID": NY})
        self.assertIs(v.kind, DateTimeKind.UTC)
        self.assertIsNone(v.tzid)

    def test_malformed_values_return_none(self):
        for bad in ["", "  ", "not-a-date", "2026-03-01", "20261301T090000"]:
            self.assertIsNone(DateTimeValue.parse(bad), bad)


class TestZoneResolution(unittest.TestCase):

    def test_zoned_value_resolves_to_the_right_instant(self):
        # 2026-03-02 is EST (UTC-5).
        v = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), NY)
        self.assertEqual(v.to_utc(), datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc))

    def test_same_wall_time_across_dst_is_a_different_instant(self):
        # US DST begins 2026-03-08. The identical 9am wall reading is 14:00Z
        # before it and 13:00Z after -- the shift a naive datetime silently
        # loses, and the reason TZID has to survive a rewrite.
        before = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), NY)
        after = DateTimeValue.zoned(datetime(2026, 3, 16, 9, 0), NY)
        self.assertEqual(before.to_utc().hour, 14)
        self.assertEqual(after.to_utc().hour, 13)

    def test_vendor_prefixed_tzid_resolves(self):
        v = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0),
                                "/mozilla.org/20050126_1/America/New_York")
        self.assertTrue(v.is_resolvable)
        self.assertEqual(v.to_utc(), datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc))

    def test_unresolvable_tzid_declines_rather_than_guessing(self):
        # Outlook emits zones defined only by the file's own VTIMEZONE.
        v = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), "Customized Time Zone")
        self.assertFalse(v.is_resolvable)
        self.assertIsNone(v.to_utc())
        self.assertIsNone(v.aware())

    def test_unresolvable_tzid_still_round_trips(self):
        # Not understanding a zone is no reason to destroy the reference to it.
        # A space needs no quoting -- RFC 5545 3.1 admits WSP in paramtext.
        v = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), "Customized Time Zone")
        line = v.to_property("DTSTART")
        self.assertEqual(line, "DTSTART;TZID=Customized Time Zone:20260302T090000")
        event = to_resource(wrap(line)).components[0]
        self.assertEqual(event.dtstart.tzid, "Customized Time Zone")
        self.assertIn(line, event.to_webdav_string())


class TestWireRoundTrip(unittest.TestCase):

    def assert_survives(self, line):
        out = to_resource(wrap(line)).to_webdav_string()
        self.assertIn(line, out)
        self.assertEqual(to_resource(out).to_webdav_string(), out, "not idempotent")

    def test_zoned_dtstart_survives(self):
        self.assert_survives(f"DTSTART;TZID={NY}:20260302T090000")

    def test_all_day_dtstart_survives(self):
        self.assert_survives("DTSTART;VALUE=DATE:20260714")

    def test_floating_dtstart_survives(self):
        self.assert_survives("DTSTART:20260302T090000")

    def test_utc_dtstart_survives(self):
        self.assert_survives("DTSTART:20260302T090000Z")

    def test_zoned_recurrence_id_survives(self):
        self.assert_survives(f"RECURRENCE-ID;TZID={NY}:20260309T090000")

    def test_all_day_due_survives(self):
        out = to_resource("\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
            "BEGIN:VTODO", "UID:t1", "SUMMARY:s",
            "DUE;VALUE=DATE:20260714", "END:VTODO", "END:VCALENDAR"])).to_webdav_string()
        self.assertIn("DUE;VALUE=DATE:20260714", out)

    def test_a_read_modify_write_does_not_move_a_zoned_event(self):
        resource = to_resource(wrap(f"DTSTART;TZID={NY}:20260302T090000"))
        before = resource.components[0].dtstart.to_utc()
        resource.components[0].summary = "Renamed"
        after = to_resource(resource.to_webdav_string()).components[0].dtstart.to_utc()
        self.assertEqual(before, after)


class TestExdateAndRdate(unittest.TestCase):

    def test_exdate_list_is_parsed(self):
        event = to_resource(wrap(
            "RRULE:FREQ=WEEKLY",
            f"EXDATE;TZID={NY}:20260316T090000,20260323T090000")).components[0]
        self.assertEqual(len(event.exdate), 2)
        self.assertTrue(all(e.tzid == NY for e in event.exdate))

    def test_repeated_exdate_lines_accumulate(self):
        event = to_resource(wrap("RRULE:FREQ=WEEKLY",
                                 "EXDATE:20260316T090000Z",
                                 "EXDATE:20260323T090000Z")).components[0]
        self.assertEqual(len(event.exdate), 2)

    def test_exdate_and_rdate_survive_a_rewrite(self):
        out = to_resource(wrap("RRULE:FREQ=WEEKLY",
                               "EXDATE:20260316T090000Z",
                               "RDATE:20260318T090000Z")).to_webdav_string()
        self.assertIn("EXDATE:20260316T090000Z", out)
        self.assertIn("RDATE:20260318T090000Z", out)

    def test_values_sharing_parameters_are_written_on_one_line(self):
        out = to_resource(wrap("RRULE:FREQ=WEEKLY",
                               "EXDATE:20260316T090000Z",
                               "EXDATE:20260323T090000Z")).to_webdav_string()
        self.assertIn("EXDATE:20260316T090000Z,20260323T090000Z", out)

    def test_period_valued_rdate_is_preserved_verbatim(self):
        # A PERIOD is a range, not a date-time; modelling it as one would be
        # worse than leaving it untouched.
        line = "RDATE;VALUE=PERIOD:19970101T180000Z/19970102T070000Z"
        event = to_resource(wrap(line)).components[0]
        self.assertEqual(event.rdate, [])
        self.assertIn(line, event.to_webdav_string())

    def test_exdate_values_are_hashable_for_matching(self):
        event = to_resource(wrap("RRULE:FREQ=WEEKLY",
                                 "EXDATE:20260316T090000Z")).components[0]
        excluded = set(event.exdate)
        self.assertIn(DateTimeValue.parse("20260316T090000Z"), excluded)
        self.assertNotIn(DateTimeValue.parse("20260317T090000Z"), excluded)


class TestRecurrenceUntil(unittest.TestCase):

    def test_utc_until_survives(self):
        event = to_resource(wrap("RRULE:FREQ=WEEKLY;UNTIL=20260601T130000Z")).components[0]
        self.assertIs(event.recurrence_rule.until.kind, DateTimeKind.UTC)
        self.assertIn("UNTIL=20260601T130000Z", event.to_webdav_string())

    def test_date_until_survives_for_an_all_day_series(self):
        # RFC 5545 3.3.10: UNTIL matches DTSTART's value type, so an all-day
        # series ends on a DATE and must not acquire a time.
        event = to_resource(wrap("DTSTART;VALUE=DATE:20260301",
                                 "RRULE:FREQ=YEARLY;UNTIL=20300301")).components[0]
        self.assertIs(event.recurrence_rule.until.kind, DateTimeKind.DATE)
        self.assertIn("UNTIL=20300301", event.to_webdav_string())

    def test_until_accepts_a_plain_datetime(self):
        rule = RecurrenceRule(frequency="WEEKLY",
                              until=datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc))
        self.assertIn("UNTIL=20260601T130000Z", rule.to_rrule_string())


class TestConstructionErgonomics(unittest.TestCase):
    """Plain datetimes stay valid input; only reading changed."""

    def test_naive_datetime_becomes_floating(self):
        event = VEVENT(uid="e1", dtstart=datetime(2026, 3, 1, 9, 0))
        self.assertIs(event.dtstart.kind, DateTimeKind.FLOATING)

    def test_aware_datetime_becomes_utc(self):
        event = VEVENT(uid="e1", dtstart=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc))
        self.assertIs(event.dtstart.kind, DateTimeKind.UTC)

    def test_offset_datetime_is_normalized_to_utc(self):
        event = VEVENT(uid="e1", dtstart=datetime(2026, 3, 1, 12, 0,
                                                  tzinfo=timezone(timedelta(hours=-5))))
        self.assertEqual(event.dtstart.to_wire(), "20260301T170000Z")

    def test_plain_date_becomes_an_all_day_value(self):
        event = VEVENT(uid="e1", dtstart=date(2026, 7, 14))
        self.assertIs(event.dtstart.kind, DateTimeKind.DATE)
        self.assertIn("DTSTART;VALUE=DATE:20260714", event.to_webdav_string())

    def test_wire_string_is_accepted(self):
        event = VEVENT(uid="e1", dtstart="20260301T090000Z")
        self.assertIs(event.dtstart.kind, DateTimeKind.UTC)

    def test_exdate_accepts_plain_datetimes(self):
        event = VEVENT(uid="e1", exdate=[datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)])
        self.assertIn("EXDATE:20260316T090000Z", event.to_webdav_string())

    def test_equality_with_a_plain_datetime_still_holds(self):
        event = VEVENT(uid="e1", dtstart=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(event.dtstart, datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc))

    def test_aware_and_naive_are_not_equal(self):
        # They describe different kinds of thing; calling them equal would lie.
        utc = DateTimeValue.parse("20260301T090000Z")
        self.assertNotEqual(utc, datetime(2026, 3, 1, 9, 0))

    def test_values_are_immutable(self):
        with self.assertRaises(Exception):
            DateTimeValue.parse("20260301T090000Z").value = datetime(2000, 1, 1)

    def test_inconsistent_state_is_rejected(self):
        with self.assertRaises(Exception):
            DateTimeValue(value=datetime(2026, 3, 1), kind=DateTimeKind.ZONED)
        with self.assertRaises(Exception):
            DateTimeValue(value=datetime(2026, 3, 1), kind=DateTimeKind.UTC, tzid=NY)


class TestComparison(unittest.TestCase):

    def test_ordering_within_a_zone(self):
        early = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), NY)
        late = DateTimeValue.zoned(datetime(2026, 3, 2, 17, 0), NY)
        self.assertLess(early, late)
        self.assertGreater(late, early)

    def test_ordering_compares_instants_not_wall_clocks(self):
        # 09:00 in New York is 14:00Z, so it is later than 10:00Z despite the
        # smaller wall reading.
        ny_morning = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), NY)
        utc_morning = DateTimeValue.parse("20260302T100000Z")
        self.assertLess(utc_morning, ny_morning)

    def test_mixed_kinds_sort_without_raising(self):
        values = [DateTimeValue.parse("20260302T100000Z"),
                  DateTimeValue.parse("20260301T090000"),
                  DateTimeValue.parse("20260305"),
                  DateTimeValue.zoned(datetime(2026, 3, 3, 9, 0), NY)]
        self.assertEqual(len(sorted(values)), 4)


class TestValueTypeHelpers(unittest.TestCase):

    def test_with_kind_of_matches_the_reference_form(self):
        start = DateTimeValue.zoned(datetime(2026, 3, 2, 9, 0), NY)
        end = DateTimeValue.parse("20260302T170000Z").with_kind_of(start)
        self.assertIs(end.kind, DateTimeKind.ZONED)
        self.assertEqual(end.tzid, NY)

    def test_end_of_day_is_the_exclusive_next_date(self):
        # RFC 5545 3.6.1: an all-day DTEND is the day after the last day.
        self.assertEqual(DateTimeValue.parse("20260714").end_of_day().to_wire(),
                         "20260715")

    def test_end_of_day_rejects_timed_values(self):
        with self.assertRaises(ValueError):
            DateTimeValue.parse("20260714T090000Z").end_of_day()

    def test_to_ical_is_self_describing(self):
        self.assertEqual(DateTimeValue.parse("20260301T090000Z").to_ical(),
                         "20260301T090000Z")
        self.assertEqual(DateTimeValue.parse("20260301").to_ical(),
                         "VALUE=DATE:20260301")
        self.assertEqual(DateTimeValue.zoned(datetime(2026, 3, 1, 9, 0), NY).to_ical(),
                         f"TZID={NY}:20260301T090000")


if __name__ == "__main__":
    unittest.main()
