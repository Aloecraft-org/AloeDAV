from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import EventStatus, Transparency
from aloedav.model.m01_base import CalendarItem,  VCalendar, Alarm, Attendee, RecurrenceRule, Attachment

class VEVENT(CalendarItem):
    version: Optional[str] = "2.0"

    # Event properties
    status: Optional[EventStatus] = EventStatus.CONFIRMED
    transparency: Optional[Transparency] = Transparency.OPAQUE
    priority: Optional[int] = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    location: Optional[str] = None
    attendees: Optional[list[Attendee]] = None
    duration: Optional[str] = None  # ISO 8601
    dtend: Optional[datetime] = None
    
    # Metadata
    comments: Optional[str] = None

    def update(self, update:"VEVENT"):
        super().update(update)

        if update.status:
            self.status = update.status
        if update.transparency:
            self.transparency = update.transparency
        if update.priority:
            self.priority = update.priority
        if update.location:
            self.location = update.location
        if update.attendees != None:
            # Empty List is valid input. None means ignore
            self.attendees = update.attendees
        if update.duration:
            self.duration = update.duration
        if update.dtend:
            self.dtend = update.dtend
        if update.comments:
            self.comments = update.comments