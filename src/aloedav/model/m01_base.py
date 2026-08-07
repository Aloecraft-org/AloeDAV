from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, EmailStr
from typing import Optional
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from aloedav.model.m00_constant import RecurrenceFrequency, AlarmAction, Classification
from aloedav.model.m00_constant import PhoneType, AddressType

def utc_now():
    return datetime.now(timezone.utc)

# Wire order follows RFC 5545 3.3.10 so serialization is stable. Module level
# rather than a class attribute: pydantic claims leading-underscore class
# attributes as private and they stop being plain iterables.
RRULE_WIRE_ORDER = (
    ("FREQ", "frequency"), ("UNTIL", "until"), ("COUNT", "count"),
    ("INTERVAL", "interval"), ("BYSECOND", "by_second"),
    ("BYMINUTE", "by_minute"), ("BYHOUR", "by_hour"), ("BYDAY", "by_day"),
    ("BYMONTHDAY", "by_month_day"), ("BYYEARDAY", "by_year_day"),
    ("BYWEEKNO", "by_week_no"), ("BYMONTH", "by_month"),
    ("BYSETPOS", "by_set_pos"), ("WKST", "week_start"),
)

class RecurrenceRule(BaseModel):
    """
    An RFC 5545 3.3.10 RECUR value. The BY* vocabulary is closed, so all of it
    is modelled: a partially-modelled rule is worse than an unmodelled one,
    because dropping BYDAY on a rewrite silently changes when the event recurs
    rather than merely losing detail.
    """
    frequency: RecurrenceFrequency
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    by_second: Optional[list[int]] = None
    by_minute: Optional[list[int]] = None
    by_hour: Optional[list[int]] = None
    by_day: Optional[list[str]] = None
    by_month_day: Optional[list[int]] = None
    by_year_day: Optional[list[int]] = None
    by_week_no: Optional[list[int]] = None
    by_month: Optional[list[int]] = None
    by_set_pos: Optional[list[int]] = None
    week_start: Optional[str] = None

    # RRULE parts outside the RFC vocabulary, kept verbatim as "NAME=VALUE".
    unknown_parts: list[str] = Field(default_factory=list)

    @classmethod
    def part_names(cls) -> dict[str, str]:
        """Maps the wire part name to the model field name."""
        return {name: field for name, field in RRULE_WIRE_ORDER}

    def to_rrule_string(self) -> str:
        from aloedav.model import ModelUtil
        parts = []
        for name, field in RRULE_WIRE_ORDER:
            value = getattr(self, field)
            if value is None:
                continue
            if name == "INTERVAL" and value == 1:
                continue      # 1 is the default; omit for a stable, minimal rule
            if name == "FREQ":
                parts.append(f"FREQ={value.value if hasattr(value, 'value') else value}")
            elif name == "UNTIL":
                parts.append(f"UNTIL={ModelUtil.format_dt(value)}")
            elif isinstance(value, list):
                if not value:
                    continue
                parts.append(f"{name}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{name}={value}")
        parts.extend(self.unknown_parts)
        return ";".join(parts)

class Alarm(BaseModel):
    action: Optional[AlarmAction] = AlarmAction.DISPLAY
    trigger_minutes: Optional[int] = Field(15, description="Minutes before event")
    description: Optional[str] = None

class Attendee(BaseModel):
    email: str
    name: Optional[str] = None
    role: str = "REQ-PARTICIPANT"  # REQ-PARTICIPANT, OPT-PARTICIPANT, NON-PARTICIPANT, CHAIR
    participation_status: str = "NEEDS-ACTION"  # NEEDS-ACTION, ACCEPTED, DECLINED, TENTATIVE, DELEGATED
    is_organizer: bool = False

class Phone(BaseModel):
    number: str
    type: Optional[PhoneType] = None
    is_preferred: bool = False

class Address(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    type: Optional[AddressType] = None

class Attachment(BaseModel):
    filename: str
    mime_type: str
    data: Optional[str] = None
    url: Optional[HttpUrl] = None

class VItem(BaseModel):
    uid: Optional[str] = Field(default=None, description="Unique identifier")
    extended_attributes: dict[str, str] = Field(default_factory=dict)
    version: str
    content_type: Optional[str] = None
    categories: Optional[list[str]] = []
    url: Optional[HttpUrl] = None
    filename: Optional[str] = None
    etag: Optional[str] = None
    raw_contents: Optional[str] = None

class VCalendar(VItem):
    content_type:str = "text/calendar; charset=utf-8"
    file_ext:str = "ics"
    version: str = "2.0"

    summary: Optional[str] = None
    dtstart: Optional[datetime] = None
    dtstamp: Optional[datetime] = Field(default_factory=utc_now, description="Creation timestamp")
    description: Optional[str] = None
    sequence: Optional[int] = 0
    classification: Optional[Classification] = Classification.PUBLIC
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    alarms: Optional[list[Alarm]] = []
    attachments: list[Attachment] = []

# ========================================================

class Item(BaseModel, ABC):
    uid: Optional[str] = None
    content_type: str
    file_ext: str
    version: str
    rev: Optional[str] = None
    prod_id: Optional[str] = "-//aloecraft.org//AloeDAV 1.0//EN"
    extended_attributes: Optional[dict[str, str]] = None
    categories: Optional[list[str]] = None
    etag: Optional[str] = None
    raw_contents: Optional[str] = None
    url: Optional[str] = None

    # Verbatim source lines for properties and sub-components this model does
    # not understand. Carried through unchanged so that editing an object
    # written by another client does not strip what that client put there.
    unknown_properties: list[str] = Field(default_factory=list)
    unknown_components: list[str] = Field(default_factory=list)

    def _preserved_lines(self) -> list[str]:
        """Unmodelled content, ready to append before the component's END."""
        return list(self.unknown_properties) + list(self.unknown_components)

    @abstractmethod
    def update(self, update:"Item"):
        if update.extended_attributes != None:
            # Empty List is valid input. None means ignore
            self.extended_attributes = update.extended_attributes
        if update.categories != None:
            # Empty List is valid input. None means ignore
            self.categories = update.categories

        self.etag = str(uuid4())

    def filename(self):
        return f"{self.uid}.{self.file_ext}"
    
class CalendarItem(Item):
    content_type:str = "text/calendar; charset=utf-8"
    file_ext:str = "ics"
    version: str = "2.0"

    # Unmodelled content belonging to the enclosing VCALENDAR rather than to
    # this component -- CALSCALE, METHOD, and VTIMEZONE definitions that
    # DTSTART's TZID refers to. Re-emitted at calendar level on serialization.
    calendar_properties: list[str] = Field(default_factory=list)
    calendar_components: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    dtstart: Optional[datetime] = None
    dtstamp: Optional[datetime] = Field(default_factory=utc_now, description="Creation timestamp")
    description: Optional[str] = None
    sequence: Optional[int] = 0
    classification: Optional[Classification] = Classification.PUBLIC
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    alarms: Optional[list[Alarm]] = None
    attachments: Optional[list[Attachment]] = None

    @abstractmethod
    def update(self, update:"Item"):
        super().update(update)

        if update.summary:
            self.summary = update.summary
        if update.dtstart:
            self.dtstart = update.dtstart
        if update.description:
            self.description = update.description
        if update.sequence:
            self.sequence = update.sequence
        if update.classification:
            self.classification = update.classification
        if update.organizer_name:
            self.organizer_name = update.organizer_name
        if update.organizer_email:
            self.organizer_email = update.organizer_email
        if update.recurrence_rule:
            self.recurrence_rule = update.recurrence_rule
        if update.recurrence_id:
            self.recurrence_id = update.recurrence_id

        if update.alarms != None:
            # Empty List is valid input. None means ignore
            self.alarms = update.alarms
        if update.attachments != None:
            # Empty List is valid input. None means ignore
            self.attachments = update.attachments

        self.dtstamp = datetime.now(timezone.utc)