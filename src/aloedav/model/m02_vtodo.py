from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import StrEnum
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import TodoStatus
from aloedav.model.m01_base import CalendarItem, VCalendar, RecurrenceRule, Alarm, Attendee, Attachment

class VTODO(CalendarItem):
    version: Optional[str] = "2.0"

    status: Optional[TodoStatus] = TodoStatus.NEEDS_ACTION
    priority: Optional[int] = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    percent_complete: Optional[int] = Field(0, ge=0, le=100)

    location: Optional[str] = None
    attendees: Optional[list[Attendee]] = None

    duration: Optional[str] = None

    due: Optional[datetime] = None
    completed: Optional[datetime] = None

    comments: Optional[str] = None

    def update(self, update:"VTODO"):
        super().update(update)

        if update.status:
            self.status = update.status
        if update.priority:
            self.priority = update.priority
        if update.percent_complete:
            self.percent_complete = update.percent_complete
        if update.location:
            self.location = update.location
        if update.attendees != None:
            # Empty List is valid input. None means ignore
            self.attendees = update.attendees
        if update.duration:
            self.duration = update.duration
        if update.due:
            self.due = update.due
        if update.completed:
            self.completed = update.completed
        if update.comments:
            self.comments = update.comments