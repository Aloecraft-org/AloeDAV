"""
Date-time values that keep the information determining what instant they name.

RFC 5545 has four distinct date-time values, and a bare `datetime` collapses
them into two:

    DTSTART;VALUE=DATE:20260301                     an all-day date
    DTSTART:20260301T090000                         floating -- 9am wherever
                                                    the observer happens to be
    DTSTART:20260301T090000Z                        an absolute instant
    DTSTART;TZID=America/New_York:20260301T090000   9am in a named zone

A `datetime` can hold the third (aware) and, indistinguishably, the first two
(both naive). The fourth has nowhere to put the zone reference at all, so
`TZID` was parsed and discarded and the event floated: an agent that read and
rewrote a New York meeting turned it into "9am in whatever timezone the reader
is in", which is a silent one-to-several-hour move on the user's calendar.
All-day events had the mirror-image problem -- indistinguishable from midnight,
so a birthday rewrote as a zero-length event at 00:00.

`value` holds naive wall-clock time in every case and `tzid` holds the
parameter *verbatim*. That is deliberate, and it is the fidelity-first choice:
the wire form is wall time plus a zone reference, so storing exactly those two
things round-trips byte-for-byte even when the TZID names a zone this machine
has never heard of. Outlook emits TZIDs like "Customized Time Zone" that are
defined only by the VTIMEZONE block inside the same file; canonicalizing to a
resolved zone would rewrite that reference and break it against the VTIMEZONE
we carefully preserved. Turning a value into a real instant is therefore a
separate, best-effort step -- `aware()` and `to_utc()`, which return None when
the zone cannot be resolved rather than guessing.
"""
import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator

try:
    from zoneinfo import ZoneInfo
except ImportError:                                   # pragma: no cover
    ZoneInfo = None


class DateTimeKind(StrEnum):
    """Which of the four RFC 5545 date-time forms a value is."""

    DATE = "DATE"           # VALUE=DATE -- a whole day, no time of day
    FLOATING = "FLOATING"   # no zone: the same clock reading everywhere
    UTC = "UTC"             # trailing 'Z' -- an absolute instant
    ZONED = "ZONED"         # TZID=... -- wall time in a named zone


def _resolve_tzid(tzid: str) -> Optional[tzinfo]:
    """
    Best-effort IANA lookup for a TZID parameter.

    Returns None rather than a fallback zone: a wrong zone silently shifts the
    user's appointments, which is worse than declining to answer.
    """
    if not tzid or ZoneInfo is None:
        return None

    candidates = [tzid]
    # Clients may namespace the identifier, e.g. Mozilla's
    # "/mozilla.org/20050126_1/America/New_York". The trailing segments are the
    # Olson name.
    if tzid.startswith("/"):
        segments = [s for s in tzid.split("/") if s]
        if len(segments) >= 2:
            candidates.append("/".join(segments[-2:]))
        if segments:
            candidates.append(segments[-1])

    for candidate in candidates:
        try:
            return ZoneInfo(candidate)
        except Exception:
            # Unknown zone, malformed name, or no tzdata installed. Windows
            # style names ("Eastern Standard Time") and file-local custom zones
            # land here; interpreting those needs the VTIMEZONE block, which is
            # preserved verbatim but not yet modelled.
            continue
    return None


class DateTimeValue(BaseModel):
    """One RFC 5545 DATE or DATE-TIME, with the zone information it arrived with."""

    # Immutable: a value type that can be mutated in place cannot safely be a
    # dict key or set member, and EXDATE matching wants exactly that.
    model_config = ConfigDict(frozen=True)

    value: datetime
    kind: DateTimeKind = DateTimeKind.FLOATING
    tzid: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_plain_values(cls, data: Any) -> Any:
        """Lets a bare datetime, date or wire string stand in for a full value."""
        if isinstance(data, (datetime, date, str)):
            return cls._as_fields(data)
        return data

    @model_validator(mode="after")
    def _check_consistency(self) -> "DateTimeValue":
        if self.kind is DateTimeKind.ZONED and not self.tzid:
            raise ValueError("a ZONED value requires a tzid")
        if self.kind is not DateTimeKind.ZONED and self.tzid:
            raise ValueError(f"a {self.kind} value cannot carry a tzid")
        return self

    # ---- construction -------------------------------------------------

    @staticmethod
    def _as_fields(data) -> dict:
        if isinstance(data, str):
            parsed = DateTimeValue.parse(data)
            if parsed is None:
                raise ValueError(f"not an RFC 5545 date or date-time: {data!r}")
            return parsed.model_dump()
        if isinstance(data, datetime):
            if data.tzinfo is not None:
                return {"value": data.astimezone(timezone.utc).replace(tzinfo=None),
                        "kind": DateTimeKind.UTC}
            return {"value": data, "kind": DateTimeKind.FLOATING}
        if isinstance(data, date):
            # A plain date is a whole day. datetime is a subclass of date, so
            # this must be checked second.
            return {"value": datetime(data.year, data.month, data.day),
                    "kind": DateTimeKind.DATE}
        raise TypeError(f"cannot read a date-time from {type(data).__name__}")

    @classmethod
    def coerce(cls, data) -> Optional["DateTimeValue"]:
        """Accepts a DateTimeValue, datetime, date, wire string, dict or None."""
        if data is None or isinstance(data, cls):
            return data
        if isinstance(data, dict):
            return cls(**data)
        return cls(**cls._as_fields(data))

    @classmethod
    def all_day(cls, value) -> "DateTimeValue":
        return cls(value=_midnight(value), kind=DateTimeKind.DATE)

    @classmethod
    def floating(cls, value: datetime) -> "DateTimeValue":
        return cls(value=value.replace(tzinfo=None), kind=DateTimeKind.FLOATING)

    @classmethod
    def utc(cls, value: datetime) -> "DateTimeValue":
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return cls(value=value.replace(tzinfo=None), kind=DateTimeKind.UTC)

    @classmethod
    def zoned(cls, value: datetime, tzid: str) -> "DateTimeValue":
        """Wall-clock `value` as read in the zone named by `tzid`."""
        return cls(value=value.replace(tzinfo=None), kind=DateTimeKind.ZONED, tzid=tzid)

    # ---- parsing ------------------------------------------------------

    @classmethod
    def parse(cls, text, params: dict = None) -> Optional["DateTimeValue"]:
        """
        Reads one wire value plus the parameters of the property carrying it.

        Returns None for anything unparseable, so a malformed date is not
        silently replaced by a plausible wrong one.
        """
        if text is None:
            return None
        text = str(text).strip()
        if not text:
            return None

        params = params or {}
        declared = str(params.get("VALUE", "") or "").upper()
        tzid = params.get("TZID")
        if tzid is True:                       # a bare "TZID" with no value
            tzid = None

        if text.endswith("Z"):
            # RFC 5545 3.3.5: a UTC value takes no TZID. Some clients send one
            # anyway; the 'Z' wins, since it is unambiguous and the TZID is not.
            parsed = _strptime(text[:-1], "%Y%m%dT%H%M%S")
            return cls(value=parsed, kind=DateTimeKind.UTC) if parsed else None

        if declared == "DATE" or (len(text) == 8 and "T" not in text):
            parsed = _strptime(text, "%Y%m%d")
            return cls(value=parsed, kind=DateTimeKind.DATE) if parsed else None

        parsed = _strptime(text, "%Y%m%dT%H%M%S")
        if parsed is None:
            return None
        if tzid:
            return cls(value=parsed, kind=DateTimeKind.ZONED, tzid=str(tzid))
        return cls(value=parsed, kind=DateTimeKind.FLOATING)

    @classmethod
    def parse_list(cls, text, params: dict = None) -> list["DateTimeValue"]:
        """Reads a comma-separated value list -- EXDATE and RDATE carry these."""
        if not text:
            return []
        values = [cls.parse(part, params) for part in str(text).split(",")]
        return [v for v in values if v is not None]

    # ---- serialization ------------------------------------------------

    def to_wire(self) -> str:
        """The value as it appears after the colon."""
        if self.kind is DateTimeKind.DATE:
            return self.value.strftime("%Y%m%d")
        if self.kind is DateTimeKind.UTC:
            return self.value.strftime("%Y%m%dT%H%M%SZ")
        return self.value.strftime("%Y%m%dT%H%M%S")

    def wire_params(self) -> str:
        """The parameters this value needs, e.g. ';TZID=America/New_York'."""
        from aloedav.model import ModelUtil

        if self.kind is DateTimeKind.DATE:
            return ";VALUE=DATE"
        if self.kind is DateTimeKind.ZONED:
            return f";TZID={ModelUtil.escape_param(self.tzid)}"
        return ""

    def to_ical(self) -> str:
        """
        The value together with its parameters, as one string:
        "20260301T090000Z", "VALUE=DATE:20260301",
        "TZID=America/New_York:20260301T090000".
        """
        params = self.wire_params()
        return f"{params.lstrip(';')}:{self.to_wire()}" if params else self.to_wire()

    def to_property(self, name: str) -> str:
        """A complete content line, parameters included."""
        return f"{name}{self.wire_params()}:{self.to_wire()}"

    @staticmethod
    def list_to_properties(name: str, values: list["DateTimeValue"]) -> list[str]:
        """
        Serializes a value list as one line per distinct parameter set, since
        every value on a line shares that line's TZID and VALUE.
        """
        lines, groups = [], {}
        for value in values or []:
            groups.setdefault((value.kind, value.tzid), []).append(value)
        for (kind, tzid), group in groups.items():
            head = group[0]
            joined = ",".join(v.to_wire() for v in group)
            lines.append(f"{name}{head.wire_params()}:{joined}")
        return lines

    # ---- interpretation -----------------------------------------------

    def zone(self) -> Optional[tzinfo]:
        """The value's zone, or None when it has none or it cannot be resolved."""
        if self.kind is DateTimeKind.UTC:
            return timezone.utc
        if self.kind is DateTimeKind.ZONED:
            return _resolve_tzid(self.tzid)
        return None

    @property
    def is_resolvable(self) -> bool:
        """Whether this value names an instant this machine can actually locate."""
        return self.zone() is not None

    def aware(self) -> Optional[datetime]:
        """
        The value as an aware datetime, or None when it does not name an
        instant -- a floating time and an all-day date genuinely do not, and a
        ZONED value whose TZID this machine cannot resolve does not either.
        """
        zone = self.zone()
        return self.value.replace(tzinfo=zone) if zone else None

    def to_utc(self) -> Optional[datetime]:
        aware = self.aware()
        return aware.astimezone(timezone.utc) if aware else None

    def date(self) -> date:
        return self.value.date()

    def end_of_day(self) -> "DateTimeValue":
        """The exclusive end of an all-day value, which DTEND expects."""
        if self.kind is not DateTimeKind.DATE:
            raise ValueError("end_of_day applies to all-day values only")
        return DateTimeValue(value=self.value + timedelta(days=1), kind=DateTimeKind.DATE)

    def with_kind_of(self, other: "DateTimeValue") -> "DateTimeValue":
        """
        This value re-expressed in `other`'s form. RFC 5545 requires DTEND to
        match DTSTART's value type, and RECURRENCE-ID to match the master's.
        """
        if other.kind is DateTimeKind.ZONED:
            return DateTimeValue.zoned(self.value, other.tzid)
        if other.kind is DateTimeKind.DATE:
            return DateTimeValue.all_day(self.value)
        if other.kind is DateTimeKind.UTC:
            return DateTimeValue(value=self.value, kind=DateTimeKind.UTC)
        return DateTimeValue.floating(self.value)

    # ---- comparison ---------------------------------------------------

    def _comparable(self) -> datetime:
        """
        A datetime that can be compared with others of the same awareness.
        Resolvable values compare as instants; the rest compare as wall time,
        which is the only thing they actually assert.
        """
        return self.aware() or self.value

    def __eq__(self, other) -> bool:
        if isinstance(other, DateTimeValue):
            return (self.kind, self.value, self.tzid) == (other.kind, other.value, other.tzid)
        if isinstance(other, datetime):
            mine = self._comparable()
            # An aware value and a naive one describe different kinds of thing;
            # comparing them would raise, and treating them as equal would be a
            # lie, so they are simply unequal.
            if (mine.tzinfo is None) != (other.tzinfo is None):
                return False
            return mine == other
        if isinstance(other, date):
            return self.kind is DateTimeKind.DATE and self.value.date() == other
        return NotImplemented

    def __lt__(self, other) -> bool:
        mine, theirs = self._comparable(), _other_comparable(other)
        if theirs is None:
            return NotImplemented
        if (mine.tzinfo is None) != (theirs.tzinfo is None):
            # Fall back to wall time; ordering floating against absolute values
            # is approximate by nature, but raising would make sorting a mixed
            # calendar impossible.
            mine = mine.replace(tzinfo=None)
            theirs = theirs.replace(tzinfo=None)
        return mine < theirs

    def __le__(self, other) -> bool:
        return self == other or self < other

    def __gt__(self, other) -> bool:
        result = self.__le__(other)
        return NotImplemented if result is NotImplemented else not result

    def __ge__(self, other) -> bool:
        result = self.__lt__(other)
        return NotImplemented if result is NotImplemented else not result

    def __hash__(self) -> int:
        return hash((self.kind, self.value, self.tzid))

    def __str__(self) -> str:
        return self.to_wire()

    def __repr__(self) -> str:
        zone = f", tzid={self.tzid!r}" if self.tzid else ""
        return f"DateTimeValue({self.to_wire()!r}, {self.kind.value}{zone})"


# RFC 5545 3.3.6: P[n]W | P[n]D[T[n]H[n]M[n]S], optionally signed.
_DURATION = re.compile(
    r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(text) -> Optional[timedelta]:
    """
    Reads an RFC 5545 DURATION into a timedelta, or None if it is not one.

    Needed to place the end of an instance whose component gives a length
    rather than a DTEND.
    """
    if text is None:
        return None
    if isinstance(text, timedelta):
        return text
    match = _DURATION.match(str(text).strip().upper())
    if not match:
        return None
    sign, weeks, days, hours, minutes, seconds = match.groups()
    if not any((weeks, days, hours, minutes, seconds)):
        return None
    length = timedelta(weeks=int(weeks or 0), days=int(days or 0),
                       hours=int(hours or 0), minutes=int(minutes or 0),
                       seconds=int(seconds or 0))
    return -length if sign == "-" else length


def _midnight(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return datetime(value.year, value.month, value.day)


def _strptime(text: str, fmt: str) -> Optional[datetime]:
    try:
        return datetime.strptime(text, fmt)
    except ValueError:
        return None


def _other_comparable(other) -> Optional[datetime]:
    if isinstance(other, DateTimeValue):
        return other._comparable()
    if isinstance(other, datetime):
        return other
    if isinstance(other, date):
        return datetime(other.year, other.month, other.day)
    return None
