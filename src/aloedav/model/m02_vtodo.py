from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import StrEnum
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import TodoStatus
from aloedav.model.m01_base import CalendarItem, VCalendar, RecurrenceRule, Alarm, Attendee, Attachment

class VTODO(CalendarItem):
    status: Optional[TodoStatus] = TodoStatus.NEEDS_ACTION
    priority: Optional[int] = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    percent_complete: Optional[int] = Field(0, ge=0, le=100)

    location: Optional[str] = None
    attendees: Optional[list[Attendee]] = None

    duration: Optional[str] = None
    related_to: Optional[str] = None
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

    def to_vtodo_string(self) -> str:
        """
        Serializes the task into a valid iCalendar (ICS) string with a VTODO component.
        """
        from uuid import uuid4

        lines = ["BEGIN:VTODO"]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
        if not self.uid:
            self.uid = f"task-{uuid4()}"
        lines.append(f"UID:{self.uid}")
        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")
        lines.append(f"SUMMARY:{self.summary}")
        
        if self.dtstart:
            lines.append(f"DTSTART:{format_dt(self.dtstart)}")
            
        # VTODO specific: DUE takes precedence over DURATION
        if self.due:
            lines.append(f"DUE:{format_dt(self.due)}")
        elif self.duration:
            lines.append(f"DURATION:{self.duration}")

        if self.completed:
            lines.append(f"COMPLETED:{format_dt(self.completed)}")

        # --- Details ---
        if self.description:
            lines.append(f"DESCRIPTION:{self.description}")
        if self.location:
            lines.append(f"LOCATION:{self.location}")
        if self.url:
            lines.append(f"URL:{self.url}")
        if self.categories:
            lines.append(f"CATEGORIES:{','.join(self.categories)}")
        
        for k, v in self.extended_attributes.items():
            lines.append(f"{k}:{v}")

        # --- Status & Priority ---
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
        lines.append(f"PRIORITY:{self.priority}")
        lines.append(f"PERCENT-COMPLETE:{self.percent_complete}")
        lines.append(f"SEQUENCE:{self.sequence}")

        # --- Organizer ---
        if self.organizer_email:
            cn_param = f";CN={self.organizer_name}" if self.organizer_name else ""
            lines.append(f"ORGANIZER{cn_param}:mailto:{self.organizer_email}")

        # --- Attendees ---
        for attendee in self.attendees:
            params = []
            params.append(f"ROLE={attendee.role}")
            params.append(f"PARTSTAT={attendee.participation_status}")
            if attendee.name:
                params.append(f"CN={attendee.name}")
            
            lines.append(f"ATTENDEE;{';'.join(params)}:mailto:{attendee.email}")

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

        # --- Alarms (VALARM) ---
        for alarm in self.alarms:
            lines.append(f"""BEGIN:VALARM
ACTION:{alarm.action}
TRIGGER:-PT{alarm.trigger_minutes}M
DESCRIPTION:{alarm.description if alarm.description else (self.summary or "Journal Reminder")}
END:VALARM""")

        lines.append("END:VTODO")
        
        return "\r\n".join(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the task into a valid iCalendar (ICS) string.
        """
        lines = [f"""
BEGIN:VCALENDAR
VERSION:{self.version}
PRODID:{self.prod_id}"""]

        lines += self.to_vtodo_string()
        lines.append("END:VCALENDAR")

        return "\r\n".join(lines)

    def to_webdav_string(self) -> str:
        return self.to_vcalendar_string()