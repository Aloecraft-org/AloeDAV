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

        esc = ModelUtil.escape_text
        param = ModelUtil.escape_param
        format_dt = ModelUtil.format_dt

        lines = ["BEGIN:VTODO"]

        # --- Core Properties ---
        if not self.uid:
            self.uid = f"task-{uuid4()}"
        lines.append(f"UID:{esc(self.uid)}")
        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")
        lines.append(f"SUMMARY:{esc(self.summary)}")

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
            lines.append(f"DESCRIPTION:{esc(self.description)}")
        if self.location:
            lines.append(f"LOCATION:{esc(self.location)}")
        if self.url:
            lines.append(f"URL:{esc(self.url)}")
        if self.categories:
            lines.append(f"CATEGORIES:{','.join(esc(c) for c in self.categories)}")

        if self.extended_attributes:
            for k, v in self.extended_attributes.items():
                lines.append(f"{k}:{esc(v)}")

        # --- Status & Priority ---
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
        lines.append(f"PRIORITY:{self.priority}")
        lines.append(f"PERCENT-COMPLETE:{self.percent_complete}")
        lines.append(f"SEQUENCE:{self.sequence}")

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
            lines.append(f"RRULE:{self.recurrence_rule.to_rrule_string()}")

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

        # Anything the model does not understand, put back untouched.
        lines.extend(self._preserved_lines())
        lines.append("END:VTODO")

        return ModelUtil.join_lines(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the task into a valid iCalendar (ICS) string.
        """
        lines = [
            "BEGIN:VCALENDAR",
            f"VERSION:{self.version}",
            f"PRODID:{ModelUtil.escape_text(self.prod_id)}",
            *self.calendar_properties,
            *self.calendar_components,
            self.to_vtodo_string(),
            "END:VCALENDAR",
        ]

        return ModelUtil.join_lines(lines)

    def to_webdav_string(self) -> str:
        return self.to_vcalendar_string()