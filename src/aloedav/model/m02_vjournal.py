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

        esc = ModelUtil.escape_text
        param = ModelUtil.escape_param
        format_dt = ModelUtil.format_dt

        lines = [ "BEGIN:VJOURNAL" ]

        # --- Core Properties ---
        # Ensure UID exists
        if not self.uid:
            self.uid = f"memo-{uuid4()}"
        lines.append(f"UID:{esc(self.uid)}")
        lines.append(f"DTSTAMP:{format_dt(self.dtstamp)}")

        if self.summary:
            lines.append(f"SUMMARY:{esc(self.summary)}")

        # VJOURNAL entries represent a specific date/time
        if self.dtstart:
            lines.append(self.dtstart.to_property("DTSTART"))

        # --- Content ---
        if self.description:
            lines.append(f"DESCRIPTION:{esc(self.description)}")

        if self.url:
            lines.append(f"URL:{esc(self.url)}")

        # Combine categories and tags for the CATEGORIES property, preserving
        # order so the serialization is stable across calls.
        all_categories = list(self.categories or [])
        all_categories.extend(self.tags or [])

        if all_categories:
            unique_cats = list(dict.fromkeys(all_categories))
            lines.append(f"CATEGORIES:{','.join(esc(c) for c in unique_cats)}")

        if self.extended_attributes:
            for k, v in self.extended_attributes.items():
                lines.append(f"{k}:{esc(v)}")

        # --- Status & Classification ---
        lines.append(f"STATUS:{self.status.value if hasattr(self.status, 'value') else self.status}")
        lines.append(f"CLASS:{self.classification.value if hasattr(self.classification, 'value') else self.classification}")
        lines.append(f"SEQUENCE:{self.sequence}")

        # --- Organizer ---
        if self.organizer_email:
            cn_param = f";CN={param(self.organizer_name)}" if self.organizer_name else ""
            lines.append(f"ORGANIZER{cn_param}:mailto:{self.organizer_email}")

        # --- Relations ---
        if self.related_to:
            lines.append(f"RELATED-TO:{esc(self.related_to)}")

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

        # Instances subtracted from and added to the generated series.
        from aloedav.model.m00_datetime import DateTimeValue
        lines.extend(DateTimeValue.list_to_properties("EXDATE", self.exdate))
        lines.extend(DateTimeValue.list_to_properties("RDATE", self.rdate))

        # --- Recurrence ID (if this is an override of a recurring entry) ---
        if self.recurrence_id:
            lines.append(self.recurrence_id.to_property("RECURRENCE-ID"))

        # --- Alarms (VALARM) ---
        # While less common for journals, they are valid (e.g., "Time to write your entry!")
        if self.alarms:
            for alarm in self.alarms:
                lines.extend([
                    "BEGIN:VALARM",
                    f"ACTION:{alarm.action}",
                    f"TRIGGER:-PT{alarm.trigger_minutes}M",
                    f"DESCRIPTION:{esc(alarm.description or self.summary or 'Journal Reminder')}",
                    "END:VALARM",
                ])

        # Anything the model does not understand, put back untouched.
        lines.extend(self._preserved_lines())
        lines.append("END:VJOURNAL")
        return ModelUtil.join_lines(lines)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the journal into a valid iCalendar (ICS) string.
        """
        lines = [
            "BEGIN:VCALENDAR",
            f"VERSION:{self.version}",
            f"PRODID:{ModelUtil.escape_text(self.prod_id)}",
            *self.calendar_properties,
            *self.calendar_components,
            self.to_vjournal_string(),
            "END:VCALENDAR",
        ]

        return ModelUtil.join_lines(lines)

    def to_component_string(self) -> str:
        """This component alone, without the VCALENDAR wrapper."""
        return self.to_vjournal_string()

    def to_webdav_string(self) -> str:
        return self.to_vcalendar_string()