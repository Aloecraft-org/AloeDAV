from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import EventStatus, Transparency
from aloedav.model.m01_base import CalendarItem,  VCalendar, Alarm, Attendee, RecurrenceRule, Attachment

class VEVENT(CalendarItem):
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


    def to_vevent_string(self) -> str:
        from uuid import uuid4
        from datetime import datetime, timezone
        lines = [
            "BEGIN:VEVENT"
        ]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            # Note: For robust timezone handling, you would normally check for 
            # tzinfo and append 'Z' for UTC. Here we assume naive = local/floating.
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
        # Ensure UID exists
        if not self.uid:
            self.uid = f"event-{uuid4()}"
        lines.append(f"UID:{self.uid}")

        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")
        lines.append(f"DTSTART:{format_dt(self.dtstart)}")
        
        if self.dtend:
            lines.append(f"DTEND:{format_dt(self.dtend)}")
        elif self.duration:
            lines.append(f"DURATION:{self.duration}")

        lines.append(f"SUMMARY:{self.summary}")
        
        if self.description:
            lines.append(f"DESCRIPTION:{self.description}")
        if self.location:
            lines.append(f"LOCATION:{self.location}")
        if self.url:
            lines.append(f"URL:{self.url}")
            
        # Ensure Enum values are serialized, not the Enum object repr
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
        lines.append(f"TRANSP:{self.transparency.value if hasattr(self.transparency, 'value') else self.transparency}")
        lines.append(f"SEQUENCE:{self.sequence}")
        lines.append(f"PRIORITY:{self.priority}")
        
        if self.categories:
            lines.append(f"CATEGORIES:{','.join(self.categories)}")
            
        for k, v in self.extended_attributes.items():
            lines.append(f"{k}:{v}")            

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
            
            # List-based rules
            if r.by_month:
                parts.append(f"BYMONTH={','.join(map(str, r.by_month))}")
            if r.by_month_day:
                parts.append(f"BYMONTHDAY={','.join(map(str, r.by_month_day))}")
            if r.by_day:
                parts.append(f"BYDAY={','.join(r.by_day)}")
            if r.by_hour:
                parts.append(f"BYHOUR={','.join(map(str, r.by_hour))}")
            
            lines.append(f"RRULE:{';'.join(parts)}")

        # --- Alarms (VALARM) ---
        for alarm in self.alarms:
            lines.append(f"""BEGIN:VALARM
ACTION:{alarm.action}
TRIGGER:-PT{alarm.trigger_minutes}M
DESCRIPTION:{alarm.description if alarm.description else (self.summary or "Journal Reminder")}
END:VALARM""")

        lines.append("END:VEVENT")
        
        return "\r\n".join(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the event into a valid iCalendar (ICS) string.
        """
        lines = [f"""
BEGIN:VCALENDAR
VERSION:{self.version}
PRODID:{self.prod_id}"""]

        lines += self.to_vevent_string()
        lines.append("END:VCALENDAR")

        return "\r\n".join(lines)
