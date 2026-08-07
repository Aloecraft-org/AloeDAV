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

        esc = ModelUtil.escape_text
        param = ModelUtil.escape_param
        format_dt = ModelUtil.format_dt

        lines = ["BEGIN:VEVENT"]

        # --- Core Properties ---
        # Ensure UID exists
        if not self.uid:
            self.uid = f"event-{uuid4()}"
        lines.append(f"UID:{esc(self.uid)}")

        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")
        if self.dtstart:
            lines.append(f"DTSTART:{format_dt(self.dtstart)}")

        if self.dtend:
            lines.append(f"DTEND:{format_dt(self.dtend)}")
        elif self.duration:
            lines.append(f"DURATION:{self.duration}")

        lines.append(f"SUMMARY:{esc(self.summary)}")

        if self.description:
            lines.append(f"DESCRIPTION:{esc(self.description)}")
        if self.location:
            lines.append(f"LOCATION:{esc(self.location)}")
        if self.url:
            lines.append(f"URL:{esc(self.url)}")

        # Ensure Enum values are serialized, not the Enum object repr
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
        lines.append(f"TRANSP:{self.transparency.value if hasattr(self.transparency, 'value') else self.transparency}")
        lines.append(f"SEQUENCE:{self.sequence}")
        lines.append(f"PRIORITY:{self.priority}")
        
        if self.categories:
            lines.append(f"CATEGORIES:{','.join(esc(c) for c in self.categories)}")

        if self.extended_attributes:
            for k, v in self.extended_attributes.items():
                lines.append(f"{k}:{esc(v)}")

        # --- Organizer ---
        if self.organizer_email:
            cn_param = f";CN={param(self.organizer_name)}" if self.organizer_name else ""
            lines.append(f"ORGANIZER{cn_param}:mailto:{self.organizer_email}")

        # --- Attendees ---
        if self.attendees:
            for attendee in self.attendees:
                params = []
                params.append(f"ROLE={param(attendee.role)}")
                params.append(f"PARTSTAT={param(attendee.participation_status)}")
                if attendee.name:
                    params.append(f"CN={param(attendee.name)}")

                lines.append(f"ATTENDEE;{';'.join(params)}:mailto:{attendee.email}")

        # --- Attachments ---
        # Note: Inline binary data is possible but discouraged for large files.
        # This implementation prefers URL references if available.
        if self.attachments:
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
        if self.alarms:
            for alarm in self.alarms:
                lines.extend([
                    "BEGIN:VALARM",
                    f"ACTION:{alarm.action}",
                    f"TRIGGER:-PT{alarm.trigger_minutes}M",
                    f"DESCRIPTION:{esc(alarm.description or self.summary or 'Reminder')}",
                    "END:VALARM",
                ])

        lines.append("END:VEVENT")

        return ModelUtil.join_lines(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the event into a valid iCalendar (ICS) string.
        """
        lines = [
            "BEGIN:VCALENDAR",
            f"VERSION:{self.version}",
            f"PRODID:{ModelUtil.escape_text(self.prod_id)}",
            self.to_vevent_string(),
            "END:VCALENDAR",
        ]

        return ModelUtil.join_lines(lines)

    def to_webdav_string(self) -> str:
        return self.to_vcalendar_string()