"""
Turning a recurring component into the concrete instances it stands for.

A stored resource says "every Monday at 9, except the 16th, and the 9th moved
to 11". Answering "what is on Thursday" or evaluating a CalDAV `time-range`
filter means turning that into actual instances, which is what `expand` does.

Expansion runs in the master's own wall-clock frame and re-attaches its zone
afterwards, rather than converting to UTC first. That ordering is what makes
DST come out right: a weekly 9am meeting in New York is 14:00Z before the March
transition and 13:00Z after it, and only an expansion that generates "9am" and
*then* resolves the zone produces both. Generating 14:00Z and adding a week
repeatedly produces a meeting that drifts an hour into the user's morning.
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

from dateutil.rrule import (DAILY, HOURLY, MINUTELY, MONTHLY, SECONDLY, WEEKLY,
                            YEARLY, MO, TU, WE, TH, FR, SA, SU, rrule)
from pydantic import BaseModel, ConfigDict

from aloedav.model.m00_datetime import DateTimeValue, DateTimeKind, parse_duration
from aloedav.model.m01_base import CalendarItem, RecurrenceRule

# The cap exists because an RRULE without COUNT or UNTIL is infinite; a caller
# that asks for no window would otherwise never get an answer.
DEFAULT_LIMIT = 1000

_FREQUENCIES = {"SECONDLY": SECONDLY, "MINUTELY": MINUTELY, "HOURLY": HOURLY,
                "DAILY": DAILY, "WEEKLY": WEEKLY, "MONTHLY": MONTHLY,
                "YEARLY": YEARLY}

_WEEKDAYS = {"MO": MO, "TU": TU, "WE": WE, "TH": TH, "FR": FR, "SA": SA, "SU": SU}

_BY_PARTS = (("by_second", "bysecond"), ("by_minute", "byminute"),
             ("by_hour", "byhour"), ("by_month_day", "bymonthday"),
             ("by_year_day", "byyearday"), ("by_week_no", "byweekno"),
             ("by_month", "bymonth"), ("by_set_pos", "bysetpos"))


class Occurrence(BaseModel):
    """One concrete instance of a component, recurring or not."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    start: DateTimeValue
    end: Optional[DateTimeValue] = None
    component: CalendarItem

    # The instance this occurrence stands at within its series. None when the
    # component does not recur at all, which is what distinguishes a one-off
    # from the first instance of a series.
    recurrence_id: Optional[DateTimeValue] = None

    # True when a stored override replaced the generated instance, so callers
    # can tell an edited instance from one the rule produced.
    is_override: bool = False

    @property
    def uid(self) -> Optional[str]:
        return self.component.uid

    @property
    def summary(self) -> Optional[str]:
        return self.component.summary

    def starts_utc(self) -> datetime:
        """A comparable instant, reading unzoned values as UTC."""
        return _utc_key(self.start)

    def __repr__(self) -> str:
        moved = " (overridden)" if self.is_override else ""
        return f"<Occurrence {self.start.to_wire()} {self.summary!r}{moved}>"


def expand(source, start=None, end=None, limit: int = DEFAULT_LIMIT) -> list[Occurrence]:
    """
    Expands a resource, a component, or a list of components into instances.

    `start` and `end` bound the result; either may be omitted, though an
    unbounded window over an infinite rule stops at `limit`. Bounds may be
    plain datetimes -- naive ones are read as UTC.
    """
    components = _components_of(source)
    window = (_utc_bound(start), _utc_bound(end))

    occurrences = []
    for _uid, group in _group_by_uid(components).items():
        occurrences.extend(_expand_series(group, window, limit))
    occurrences.sort(key=lambda o: o.starts_utc())
    return occurrences


def _components_of(source) -> list[CalendarItem]:
    if isinstance(source, CalendarItem):
        return [source]
    if isinstance(source, (list, tuple)):
        return list(source)
    # A resource, or anything else exposing its components.
    return list(getattr(source, "components", []) or [])


def _group_by_uid(components) -> dict:
    """
    Groups components into series.

    Keyed by UID because one resource may legitimately carry several -- a
    plain .ics file is not bound by the one-UID rule CalDAV imposes on a
    resource, and a mixed file must still expand correctly.
    """
    groups = {}
    for component in components:
        groups.setdefault(component.uid, []).append(component)
    return groups


def _expand_series(group: list[CalendarItem], window, limit: int) -> list[Occurrence]:
    master = next((c for c in group if c.recurrence_id is None), None)
    overrides = [c for c in group if c.recurrence_id is not None]

    # A series with no master is not malformed -- a client may hold only the
    # override for an instance whose master lives in another resource.
    if master is None:
        return [o for o in (_occurrence_from(c, c.recurrence_id, True) for c in overrides)
                if _within(o, window)]

    if master.dtstart is None:
        return []

    by_recurrence_id = {_match_key(c.recurrence_id): c for c in overrides}
    starts = _instance_starts(master, window, limit)
    # Only a component that actually repeats has instances to identify; a
    # one-off carries no RECURRENCE-ID.
    recurring = master.recurrence_rule is not None or bool(master.rdate)

    occurrences = []
    claimed = set()
    for instance in starts:
        key = _match_key(instance)
        override = by_recurrence_id.get(key)
        if override is not None:
            claimed.add(key)
            occurrences.append(_occurrence_from(override, instance, True))
        else:
            occurrences.append(_occurrence_from(master, instance, False, recurring=recurring))

    # An override whose RECURRENCE-ID the rule does not generate is still real:
    # the client stored it deliberately, and dropping it would hide an event.
    for override in overrides:
        if _match_key(override.recurrence_id) not in claimed:
            occurrences.append(_occurrence_from(override, override.recurrence_id, True))

    return [o for o in occurrences if _within(o, window)]


def _instance_starts(master: CalendarItem, window, limit: int) -> list[DateTimeValue]:
    """Every start time the rule produces, minus EXDATE, plus RDATE."""
    anchor = master.dtstart
    starts: list[datetime] = []

    if master.recurrence_rule is not None:
        rule = _build_rrule(master.recurrence_rule, anchor)
        if rule is not None:
            starts.extend(_take(rule, anchor, window, limit))
    else:
        starts.append(anchor.value)

    # RDATE adds instances the rule does not generate.
    starts.extend(d.value for d in (master.rdate or []))

    excluded = {_match_key(d) for d in (master.exdate or [])}
    seen, result = set(), []
    for naive in sorted(starts):
        instance = DateTimeValue(value=naive, kind=anchor.kind, tzid=anchor.tzid)
        key = _match_key(instance)
        if key in excluded or key in seen:
            continue
        seen.add(key)
        result.append(instance)
        if len(result) >= limit:
            break
    return result


def _build_rrule(rule: RecurrenceRule, anchor: DateTimeValue) -> Optional[rrule]:
    frequency = _FREQUENCIES.get(str(getattr(rule.frequency, "value", rule.frequency)).upper())
    if frequency is None:
        return None

    kwargs = {"dtstart": anchor.value, "interval": rule.interval or 1}
    if rule.count:
        kwargs["count"] = rule.count
    if rule.until is not None:
        # UNTIL is an absolute bound but expansion runs in wall time, so it has
        # to be read into the anchor's frame or the series ends at the wrong
        # instance by the zone's offset.
        kwargs["until"] = _into_frame(_utc_key(rule.until), anchor)
    if rule.by_day:
        weekdays = [wd for wd in (_weekday(token) for token in rule.by_day) if wd]
        if weekdays:
            kwargs["byweekday"] = weekdays
    if rule.week_start:
        start_day = _weekday(rule.week_start)
        if start_day is not None:
            kwargs["wkst"] = start_day
    for field, keyword in _BY_PARTS:
        values = getattr(rule, field, None)
        if values:
            kwargs[keyword] = values

    try:
        return rrule(frequency, **kwargs)
    except (ValueError, TypeError):
        # A rule this library cannot evaluate should not take down a listing;
        # the component still round-trips, it just does not expand.
        return None


def _weekday(token: str):
    """Reads a BYDAY token: 'MO', '2FR', '-1SU'."""
    match = re.match(r"^([+-]?\d+)?([A-Z]{2})$", str(token).strip().upper())
    if not match:
        return None
    ordinal, name = match.groups()
    weekday = _WEEKDAYS.get(name)
    if weekday is None:
        return None
    return weekday(int(ordinal)) if ordinal else weekday


def _take(rule: rrule, anchor: DateTimeValue, window, limit: int) -> list[datetime]:
    """Instances within the window, in the anchor's wall-clock frame."""
    low, high = window
    if low is None and high is None:
        return list(rule[:limit])

    # between() is exclusive at both ends, so the bounds are nudged outward by
    # the longest instance the series could produce -- an event that started
    # before the window but runs into it still belongs in the answer.
    lo = _into_frame(low, anchor) - timedelta(days=1) if low else None
    hi = _into_frame(high, anchor) + timedelta(days=1) if high else None
    if lo is not None and hi is not None:
        return list(rule.between(lo, hi, inc=True))[:limit]
    if hi is not None:
        return [d for d in rule[:limit] if d <= hi]
    return [d for d in rule[:limit] if d >= lo]


def _occurrence_from(component: CalendarItem, instance: DateTimeValue,
                     is_override: bool, recurring: bool = None) -> Occurrence:
    start = component.dtstart if is_override and component.dtstart else instance
    if recurring is None:
        recurring = is_override
    return Occurrence(
        start=start,
        end=_end_of(component, start),
        component=component,
        recurrence_id=instance if (recurring or is_override) else None,
        is_override=is_override)


def _end_of(component: CalendarItem, start: DateTimeValue) -> Optional[DateTimeValue]:
    """
    When the instance finishes.

    DTEND wins, then DUE for a VTODO, then DURATION. With none of them an
    all-day value lasts one day and a timed one has no extent at all
    (RFC 5545 3.6.1).
    """
    explicit = getattr(component, "dtend", None) or getattr(component, "due", None)
    if explicit is not None:
        anchor = component.dtstart
        if anchor is not None and start != anchor:
            # A generated instance is offset from the master, so the stored end
            # applies as a length rather than as an absolute time.
            return _shift(start, explicit.value - anchor.value)
        return explicit

    length = parse_duration(getattr(component, "duration", None))
    if length is not None:
        return _shift(start, length)
    if start.kind is DateTimeKind.DATE:
        return start.end_of_day()
    return None


def _shift(start: DateTimeValue, length: timedelta) -> DateTimeValue:
    return DateTimeValue(value=start.value + length, kind=start.kind, tzid=start.tzid)


def _match_key(value: Optional[DateTimeValue]):
    """
    Identifies an instance for EXDATE and RECURRENCE-ID matching.

    Wall time is the key because that is what a conformant file uses: RFC 5545
    requires these to share DTSTART's value type and zone, so comparing wall
    readings matches without depending on a zone this machine may not resolve.
    """
    return value.value if value is not None else None


def _utc_key(value: DateTimeValue) -> datetime:
    """A comparable instant. Unzoned values are read as UTC for ordering."""
    resolved = value.to_utc()
    return resolved if resolved else value.value.replace(tzinfo=timezone.utc)


def _utc_bound(bound) -> Optional[datetime]:
    if bound is None:
        return None
    if isinstance(bound, DateTimeValue):
        return _utc_key(bound)
    if isinstance(bound, datetime):
        return bound if bound.tzinfo else bound.replace(tzinfo=timezone.utc)
    if isinstance(bound, date):
        return datetime(bound.year, bound.month, bound.day, tzinfo=timezone.utc)
    raise TypeError(f"cannot read a window bound from {type(bound).__name__}")


def _into_frame(instant: datetime, anchor: DateTimeValue) -> datetime:
    """Reads an absolute instant as a wall-clock reading in the anchor's zone."""
    zone = anchor.zone()
    if zone is None:
        return instant.replace(tzinfo=None)
    return instant.astimezone(zone).replace(tzinfo=None)


def _within(occurrence: Occurrence, window) -> bool:
    low, high = window
    start = occurrence.starts_utc()
    finish = _utc_key(occurrence.end) if occurrence.end else start
    # Half-open, per RFC 4791 9.9: an instance touching the window is in it,
    # but one that merely ends exactly at its start is not.
    if low is not None and finish <= low and finish != start:
        return False
    if low is not None and finish == start and start < low:
        return False
    if high is not None and start >= high:
        return False
    return True
