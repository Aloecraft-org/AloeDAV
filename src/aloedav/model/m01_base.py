from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from aloedav.model.m00_constant import RecurrenceFrequency, AlarmAction
from aloedav.model.m00_constant import PhoneType, AddressType

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
    url: Optional[str] = None
