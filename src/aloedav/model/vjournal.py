from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class JournalStatus(str, Enum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    CANCELLED = "CANCELLED"


class JournalClass(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    CONFIDENTIAL = "CONFIDENTIAL"


class RecurrenceFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class RecurrenceRule(BaseModel):
    frequency: RecurrenceFrequency
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    by_month_day: Optional[List[int]] = None
    by_month: Optional[List[int]] = None
    by_day: Optional[List[str]] = None


class Attachment(BaseModel):
    filename: str
    mime_type: str
    data: Optional[str] = None
    url: Optional[str] = None


class Alarm(BaseModel):
    action: str = "DISPLAY"
    trigger_minutes: int = Field(0, description="Minutes before journal date")
    description: Optional[str] = None


class VJournal(BaseModel):
    # Required fields
    uid: str = Field(..., description="Unique identifier")
    dtstamp: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    
    # Journal content
    summary: Optional[str] = None
    description: Optional[str] = Field(None, description="Main journal entry text")
    
    # Timing
    dtstart: Optional[datetime] = None
    
    # Journal properties
    status: JournalStatus = JournalStatus.DRAFT
    classification: JournalClass = JournalClass.PRIVATE
    sequence: int = 0
    
    # Organizer
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    
    # Organization
    categories: List[str] = []
    tags: List[str] = []
    
    # Related content
    attachments: List[Attachment] = []
    related_to: Optional[str] = None
    url: Optional[str] = None
    
    # Recurrence (for recurring journal entries)
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    
    # Notifications
    alarms: List[Alarm] = []
    
    # Metadata
    version: str = "2.0"
    comments: Optional[str] = None
    
    class Config:
        use_enum_values = True


    def to_vcalendar_string(self) -> str:
        """
        Serializes the journal entry into a valid iCalendar (ICS) string with a VJOURNAL component.
        """

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Vera//aloecraft.org//",
            "BEGIN:VJOURNAL"
        ]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
        lines.append(f"UID:{self.uid}")
        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")
        
        if self.summary:
            lines.append(f"SUMMARY:{self.summary}")
        
        # VJOURNAL entries represent a specific date/time
        if self.dtstart:
            lines.append(f"DTSTART:{format_dt(self.dtstart)}")

        # --- Content ---
        if self.description:
            # Ensure description is properly escaped if it contains newlines or special chars
            # Simple replacement for demonstration; a full implementation might need more robust escaping
            desc = self.description.replace("\n", "\\n")
            lines.append(f"DESCRIPTION:{desc}")

        if self.url:
            lines.append(f"URL:{self.url}")
        
        # Combine categories and tags for the CATEGORIES property
        all_categories = self.categories.copy()
        if self.tags:
            all_categories.extend(self.tags)
        
        if all_categories:
            # Remove duplicates if any
            unique_cats = list(set(all_categories))
            lines.append(f"CATEGORIES:{','.join(unique_cats)}")

        # --- Status & Classification ---
        lines.append(f"STATUS:{self.status}")
        lines.append(f"CLASS:{self.classification}")
        lines.append(f"SEQUENCE:{self.sequence}")

        # --- Organizer ---
        if self.organizer_email:
            cn_param = f";CN={self.organizer_name}" if self.organizer_name else ""
            lines.append(f"ORGANIZER{cn_param}:mailto:{self.organizer_email}")

        # --- Relations ---
        if self.related_to:
            lines.append(f"RELATED-TO:{self.related_to}")

        # --- Attachments ---
        # Note: Inline binary data is possible but discouraged for large files.
        # This implementation prefers URL references if available.
        for attachment in self.attachments:
            if attachment.url:
                lines.append(f"ATTACH;FMTTYPE={attachment.mime_type}:{attachment.url}")
            # If you needed to handle inline data, you'd base64 encode it here, 
            # but that significantly increases file size.

        # --- Recurrence Rule (RRULE) ---
        if self.recurrence_rule:
            r = self.recurrence_rule
            parts = [f"FREQ={r.frequency}"]
            
            if r.interval > 1:
                parts.append(f"INTERVAL={r.interval}")
            
            if r.count:
                parts.append(f"COUNT={r.count}")
            elif r.until:
                parts.append(f"UNTIL={format_dt(r.until)}")
            
            if r.by_month:
                parts.append(f"BYMONTH={','.join(map(str, r.by_month))}")
            if r.by_month_day:
                parts.append(f"BYMONTHDAY={','.join(map(str, r.by_month_day))}")
            if r.by_day:
                parts.append(f"BYDAY={','.join(r.by_day)}")
            
            lines.append(f"RRULE:{';'.join(parts)}")

        # --- Recurrence ID (if this is an override of a recurring entry) ---
        if self.recurrence_id:
            lines.append(f"RECURRENCE-ID:{format_dt(self.recurrence_id)}")

        # --- Alarms (VALARM) ---
        # While less common for journals, they are valid (e.g., "Time to write your entry!")
        for alarm in self.alarms:
            lines.append("BEGIN:VALARM")
            lines.append(f"ACTION:{alarm.action}")
            lines.append(f"TRIGGER:-PT{alarm.trigger_minutes}M")
            
            desc = alarm.description if alarm.description else (self.summary or "Journal Reminder")
            lines.append(f"DESCRIPTION:{desc}")
            lines.append("END:VALARM")

        lines.append("END:VJOURNAL")
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)


# Example usage
if __name__ == "__main__":
    # Single journal entry
    journal_entry = VJournal(
        uid="journal-001@example.com",
        dtstart=datetime(2026, 1, 5, 18, 30, 0),
        summary="Reflection on Q1 Planning",
        description="Today was productive. We finalized the Q1 roadmap and got buy-in from stakeholders. "
                    "The team showed great enthusiasm for the new initiatives. Need to follow up on resource allocation by end of week.",
        status=JournalStatus.FINAL,
        classification=JournalClass.PRIVATE,
        organizer_name="Vera",
        organizer_email="vera@example.com",
        categories=["WORK", "PLANNING"],
        tags=["productivity", "teamwork", "quarterly-planning"],
    )
    
    print(journal_entry.model_dump_json(indent=2))
    
    # Recurring daily journal (like a diary)
    print("\n")
    daily_journal = VJournal(
        uid="daily-journal@example.com",
        dtstart=datetime(2026, 1, 6, 22, 0, 0),
        summary="Daily Reflection",
        description="A space for daily thoughts and reflections.",
        status=JournalStatus.DRAFT,
        classification=JournalClass.PRIVATE,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.DAILY,
            interval=1,
        ),
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=120, description="Evening reflection reminder"),
        ],
        categories=["PERSONAL"],
        tags=["daily", "reflection"],
    )
    
    print(daily_journal.model_dump_json(indent=2))