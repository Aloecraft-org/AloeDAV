from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, EmailStr
from typing import Optional
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from aloedav.model.m00_constant import RecurrenceFrequency, AlarmAction, Classification
from aloedav.model.m00_constant import PhoneType, AddressType

def utc_now():
    return datetime.now(timezone.utc)

class RecurrenceRule(BaseModel):
    frequency: RecurrenceFrequency
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    by_month_day: Optional[list[int]] = None
    by_month: Optional[list[int]] = None
    by_day: Optional[list[str]] = None
    by_hour: Optional[list[int]] = None

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
    categories: Optional[list[str]] = []
    url: Optional[HttpUrl] = None
    filename: Optional[str] = None
    etag: Optional[str] = None
    raw_contents: Optional[str] = None

class VCalendar(VItem):
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
    uid: str
    file_ext: str
    version: str
    extended_attributes: Optional[dict[str, str]] = None
    categories: Optional[list[str]] = None
    etag: Optional[str] = None
    raw_contents: Optional[str] = None

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
    file_ext:str = "ics"
    version: str = "2.0"
    summary: Optional[str] = None
    dtstart: Optional[datetime] = None
    dtstamp: Optional[datetime] = Field(default_factory=utc_now, description="Creation timestamp")
    description: Optional[str] = None
    sequence: Optional[int] = None
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