from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import Classification, JournalStatus
from aloedav.model.m01_base import CalendarItem, VCalendar, RecurrenceRule, Attachment, Alarm

class VJOURNAL(CalendarItem):
    version: Optional[str] = "2.0"

    # Journal properties
    status: JournalStatus = JournalStatus.DRAFT
    tags: list[str] = None
    
    classification: Optional[Classification] = Classification.PRIVATE

    # Metadata
    related_to: Optional[str] = None
    comments: Optional[str] = None

    def update(self, update:"VJOURNAL"):
        super().update(update)

        if update.status:
            self.status = update.status
        if update.tags != None:
            self.tags = update.tags
        if update.classification:
            self.classification = update.classification
        if update.related_to:
            self.related_to = update.related_to
        if update.comments:
            self.comments = update.comments
