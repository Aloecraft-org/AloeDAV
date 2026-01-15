from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import Classification, JournalStatus
from aloedav.model.m01_base import CalendarItem, VCalendar, RecurrenceRule, Attachment, Alarm

class VJOURNAL(CalendarItem):
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


    def to_vjournal_string(self) -> str:
        """
        Serializes the journal entry into a valid iCalendar (ICS) string with a VJOURNAL component.
        """
        from uuid import uuid4

        lines = [ "BEGIN:VJOURNAL" ]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
        # Ensure UID exists
        if not self.uid:
            self.uid = f"memo-{uuid4()}"
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

        for k, v in self.extended_attributes.items():
            lines.append(f"{k}:{v}")

        # --- Status & Classification ---
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
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
            freq = r.frequency.value if hasattr(r.frequency, 'value') else r.frequency
            parts = [f"FREQ={freq}"]
            
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
            lines.append(f"""BEGIN:VALARM
ACTION:{alarm.action}
TRIGGER:-PT{alarm.trigger_minutes}M
DESCRIPTION:{alarm.description if alarm.description else (self.summary or "Journal Reminder")}
END:VALARM""")

        lines.append("END:VJOURNAL")
        return "\r\n".join(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the journal into a valid iCalendar (ICS) string.
        """
        lines = [f"""
BEGIN:VCALENDAR
VERSION:{self.version}
PRODID:{self.prod_id}"""]

        lines += self.to_vjournal_string()
        lines.append("END:VCALENDAR")

        return "\r\n".join(lines)
