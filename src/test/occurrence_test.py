"""
Recurrence expansion tests.

The cases that matter are the ones where a plausible implementation is wrong
rather than absent: an instance landing on the far side of a DST transition, an
override that moved outside the window, an EXDATE that has to match by wall
clock rather than by instant.
"""
import unittest
from datetime import date, datetime, timezone

from aloedav.model.m00_datetime import DateTimeValue, DateTimeKind, parse_duration
from aloedav.model.m03_occurrence import expand
from aloedav.model.serial_util import to_resource

NY = "America/New_York"


def cal(*component_lines):
    return to_resource("\r\n".join(
        ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
         *component_lines, "END:VCALENDAR"]))


def event(*lines, uid="e1"):
    return ["BEGIN:VEVENT", f"UID:{uid}", "SUMMARY:s", *lines, "END:VEVENT"]


def starts(occurrences):
    return [o.start.to_wire() for o in occurrences]


class TestBasicExpansion(unittest.TestCase):

    def test_non_recurring_component_yields_one_occurrence(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z")))
        self.assertEqual(len(result), 1)
        # A one-off is not the first instance of a series, and says so.
        self.assertIsNone(result[0].recurrence_id)

    def test_weekly_count(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=WEEKLY;COUNT=3")))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260309T090000Z",
                                          "20260316T090000Z"])

    def test_until_bounds_the_series(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=WEEKLY;UNTIL=20260316T090000Z")))
        self.assertEqual(len(result), 3)

    def test_recurring_instances_carry_a_recurrence_id(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=WEEKLY;COUNT=2")))
        self.assertTrue(all(o.recurrence_id is not None for o in result))

    def test_daily_interval(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=DAILY;INTERVAL=3;COUNT=3")))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260305T090000Z",
                                          "20260308T090000Z"])

    def test_monthly_by_last_friday(self):
        result = expand(cal(*event("DTSTART:20260327T090000Z",
                                   "RRULE:FREQ=MONTHLY;BYDAY=-1FR;COUNT=3")))
        self.assertEqual(starts(result), ["20260327T090000Z", "20260424T090000Z",
                                          "20260529T090000Z"])

    def test_by_set_pos(self):
        # Second Tuesday of each month.
        result = expand(cal(*event("DTSTART:20260310T090000Z",
                                   "RRULE:FREQ=MONTHLY;BYDAY=TU;BYSETPOS=2;COUNT=2")))
        self.assertEqual(starts(result), ["20260310T090000Z", "20260414T090000Z"])

    def test_infinite_rule_is_capped(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z", "RRULE:FREQ=DAILY")),
                        limit=10)
        self.assertEqual(len(result), 10)

    def test_unmodellable_rule_leaves_the_event_readable(self):
        # An RRULE this model cannot represent must not make the whole event
        # unreadable, and must not be silently dropped either: the event still
        # expands to its DTSTART and the rule survives verbatim.
        resource = cal(*event("DTSTART:20260302T090000Z", "RRULE:FREQ=NONSENSE"))
        result = expand(resource)
        self.assertEqual(starts(result), ["20260302T090000Z"])
        self.assertIn("RRULE:FREQ=NONSENSE", resource.to_webdav_string())

    def test_rule_without_a_frequency_is_preserved(self):
        resource = cal(*event("DTSTART:20260302T090000Z", "RRULE:COUNT=5"))
        self.assertIsNone(resource.components[0].recurrence_rule)
        self.assertIn("RRULE:COUNT=5", resource.to_webdav_string())


class TestTimezoneCorrectness(unittest.TestCase):

    def test_instances_hold_their_wall_time_across_dst(self):
        # US DST begins 2026-03-08. A 9am New York meeting stays 9am, which
        # means the instant moves by an hour -- expanding in UTC would instead
        # hold the instant and drift the meeting to 8am.
        result = expand(cal(*event(f"DTSTART;TZID={NY}:20260302T090000",
                                   "RRULE:FREQ=WEEKLY;COUNT=3")))
        self.assertTrue(all(o.start.value.hour == 9 for o in result))
        self.assertEqual([o.starts_utc().hour for o in result], [14, 13, 13])

    def test_expanded_instances_keep_the_zone(self):
        result = expand(cal(*event(f"DTSTART;TZID={NY}:20260302T090000",
                                   "RRULE:FREQ=WEEKLY;COUNT=2")))
        self.assertTrue(all(o.start.kind is DateTimeKind.ZONED for o in result))
        self.assertTrue(all(o.start.tzid == NY for o in result))

    def test_until_in_utc_bounds_a_zoned_series_correctly(self):
        # UNTIL is absolute while expansion runs in wall time, so it has to be
        # read into the zone or the series ends one instance early or late.
        result = expand(cal(*event(f"DTSTART;TZID={NY}:20260302T090000",
                                   "RRULE:FREQ=WEEKLY;UNTIL=20260316T140000Z")))
        self.assertEqual(len(result), 3)

    def test_all_day_series_stays_all_day(self):
        result = expand(cal(*event("DTSTART;VALUE=DATE:20260714",
                                   "RRULE:FREQ=YEARLY;COUNT=3")))
        self.assertEqual(starts(result), ["20260714", "20270714", "20280714"])
        self.assertTrue(all(o.start.kind is DateTimeKind.DATE for o in result))


class TestExdateAndRdate(unittest.TestCase):

    def test_exdate_removes_an_instance(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=WEEKLY;COUNT=3",
                                   "EXDATE:20260309T090000Z")))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260316T090000Z"])

    def test_zoned_exdate_matches_by_wall_clock(self):
        result = expand(cal(*event(f"DTSTART;TZID={NY}:20260302T090000",
                                   "RRULE:FREQ=WEEKLY;COUNT=3",
                                   f"EXDATE;TZID={NY}:20260309T090000")))
        self.assertEqual(len(result), 2)

    def test_rdate_adds_an_instance(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RRULE:FREQ=WEEKLY;COUNT=2",
                                   "RDATE:20260304T090000Z")))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260304T090000Z",
                                          "20260309T090000Z"])

    def test_rdate_without_a_rule_still_expands(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z",
                                   "RDATE:20260304T090000Z")))
        self.assertEqual(len(result), 2)


class TestOverrides(unittest.TestCase):

    MOVED = (event("DTSTART:20260302T090000Z", "RRULE:FREQ=WEEKLY;COUNT=3")
             + event("RECURRENCE-ID:20260309T090000Z", "DTSTART:20260309T110000Z",
                     "SUMMARY:Moved"))

    def test_override_replaces_the_generated_instance(self):
        result = expand(cal(*self.MOVED))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260309T110000Z",
                                          "20260316T090000Z"])

    def test_override_is_flagged(self):
        result = expand(cal(*self.MOVED))
        self.assertEqual([o.is_override for o in result], [False, True, False])
        self.assertEqual(result[1].summary, "Moved")

    def test_override_keeps_the_instance_it_replaced(self):
        # The occurrence reports where it sits in the series, not where it moved
        # to -- that is what identifies it back to the server.
        moved = expand(cal(*self.MOVED))[1]
        self.assertEqual(moved.recurrence_id.to_wire(), "20260309T090000Z")

    def test_override_outside_the_rule_is_still_reported(self):
        # A stored override the rule does not generate was put there
        # deliberately; dropping it would hide an event.
        result = expand(cal(*(event("DTSTART:20260302T090000Z",
                                    "RRULE:FREQ=WEEKLY;COUNT=2")
                              + event("RECURRENCE-ID:20260401T090000Z",
                                      "DTSTART:20260401T090000Z", "SUMMARY:Orphan"))))
        self.assertIn("Orphan", [o.summary for o in result])

    def test_override_without_a_master_is_still_reported(self):
        result = expand(cal(*event("RECURRENCE-ID:20260309T090000Z",
                                   "DTSTART:20260309T110000Z", "SUMMARY:Lonely")))
        self.assertEqual([o.summary for o in result], ["Lonely"])


class TestInstanceEnds(unittest.TestCase):

    def test_dtend_becomes_a_length_for_generated_instances(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z", "DTEND:20260302T093000Z",
                                   "RRULE:FREQ=WEEKLY;COUNT=2")))
        self.assertEqual([o.end.to_wire() for o in result],
                         ["20260302T093000Z", "20260309T093000Z"])

    def test_duration_places_the_end(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z", "DURATION:PT90M",
                                   "RRULE:FREQ=WEEKLY;COUNT=2")))
        self.assertEqual(result[0].end.to_wire(), "20260302T103000Z")

    def test_all_day_without_an_end_lasts_one_day(self):
        result = expand(cal(*event("DTSTART;VALUE=DATE:20260714")))
        self.assertEqual(result[0].end.to_wire(), "20260715")

    def test_timed_event_without_an_end_has_no_extent(self):
        result = expand(cal(*event("DTSTART:20260302T090000Z")))
        self.assertIsNone(result[0].end)

    def test_vtodo_uses_due_as_its_end(self):
        result = expand(to_resource("\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
            "BEGIN:VTODO", "UID:t1", "SUMMARY:s", "DTSTART:20260302T090000Z",
            "DUE:20260302T170000Z", "END:VTODO", "END:VCALENDAR"])))
        self.assertEqual(result[0].end.to_wire(), "20260302T170000Z")


class TestWindowing(unittest.TestCase):

    WEEKLY = event("DTSTART:20260302T090000Z", "DTEND:20260302T100000Z",
                   "RRULE:FREQ=WEEKLY;COUNT=5")

    def test_start_bound_excludes_earlier_instances(self):
        result = expand(cal(*self.WEEKLY), start=datetime(2026, 3, 16, tzinfo=timezone.utc))
        self.assertEqual(starts(result), ["20260316T090000Z", "20260323T090000Z",
                                          "20260330T090000Z"])

    def test_end_bound_excludes_later_instances(self):
        result = expand(cal(*self.WEEKLY), end=datetime(2026, 3, 16, tzinfo=timezone.utc))
        self.assertEqual(starts(result), ["20260302T090000Z", "20260309T090000Z"])

    def test_both_bounds(self):
        result = expand(cal(*self.WEEKLY),
                        start=datetime(2026, 3, 9, tzinfo=timezone.utc),
                        end=datetime(2026, 3, 24, tzinfo=timezone.utc))
        self.assertEqual(len(result), 3)

    def test_naive_bounds_are_read_as_utc(self):
        result = expand(cal(*self.WEEKLY), start=datetime(2026, 3, 16))
        self.assertEqual(len(result), 3)

    def test_date_bounds_are_accepted(self):
        result = expand(cal(*self.WEEKLY), start=date(2026, 3, 16))
        self.assertEqual(len(result), 3)

    def test_an_instance_overlapping_the_window_start_is_included(self):
        # Started before the window, still running inside it.
        result = expand(cal(*event("DTSTART:20260302T090000Z", "DTEND:20260302T170000Z")),
                        start=datetime(2026, 3, 2, 12, tzinfo=timezone.utc))
        self.assertEqual(len(result), 1)


class TestMultipleSeries(unittest.TestCase):

    def test_each_uid_expands_independently(self):
        result = expand(cal(*(event("DTSTART:20260302T090000Z",
                                    "RRULE:FREQ=WEEKLY;COUNT=2", uid="a")
                              + event("DTSTART:20260303T090000Z",
                                      "RRULE:FREQ=WEEKLY;COUNT=3", uid="b"))))
        self.assertEqual(len(result), 5)
        self.assertEqual(sorted({o.uid for o in result}), ["a", "b"])

    def test_results_are_ordered_by_instant(self):
        result = expand(cal(*(event("DTSTART:20260305T090000Z", uid="late")
                              + event("DTSTART:20260302T090000Z", uid="early"))))
        self.assertEqual([o.uid for o in result], ["early", "late"])

    def test_a_bare_component_can_be_expanded(self):
        component = cal(*event("DTSTART:20260302T090000Z",
                               "RRULE:FREQ=WEEKLY;COUNT=2")).components[0]
        self.assertEqual(len(expand(component)), 2)


class TestDurationParsing(unittest.TestCase):

    def test_forms(self):
        self.assertEqual(parse_duration("PT1H").total_seconds(), 3600)
        self.assertEqual(parse_duration("P1D").days, 1)
        self.assertEqual(parse_duration("P2W").days, 14)
        self.assertEqual(parse_duration("PT1H30M").total_seconds(), 5400)
        self.assertEqual(parse_duration("-PT15M").total_seconds(), -900)

    def test_rejects_non_durations(self):
        for bad in ["", "P", "garbage", "20260301T090000", None]:
            self.assertIsNone(parse_duration(bad), bad)


if __name__ == "__main__":
    unittest.main()
