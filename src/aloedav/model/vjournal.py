from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum
from aloedav.model.utils import unfold_lines

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
    @classmethod
    def from_vcalendar_string(cls, ics_string: str) -> "VJournal":
        lines = unfold_lines(ics_string)
        data = {
            "alarms": [],
            "categories": [],
            "tags": [],
            "attachments": []
        }
        
        current_context = "ROOT"
        current_alarm = None

        def parse_dt(val):
            # rudimentary parsing for YYYYMMDDTHHMMSS[Z]
            fmt = "%Y%m%dT%H%M%S"
            if val.endswith("Z"):
                val = val[:-1]
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                return datetime.utcnow() # Fallback

        for line in lines:
            if ":" not in line: continue
            
            key_part, value = line.split(":", 1)
            
            params = {}
            if ";" in key_part:
                parts = key_part.split(";")
                key = parts[0].upper()
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        params[k.upper()] = v
                    else:
                        params[p.upper()] = True
            else:
                key = key_part.upper()

            # State Machine
            if key == "BEGIN":
                if value == "VCALENDAR": current_context = "VCALENDAR"
                elif value == "VJOURNAL": current_context = "VJOURNAL"
                elif value == "VALARM":
                    current_context = "VALARM"
                    current_alarm = {"trigger_minutes": 0}
                continue
            elif key == "END":
                if value == "VALARM":
                    if current_alarm:
                        data["alarms"].append(Alarm(**current_alarm))
                    current_context = "VJOURNAL"
                    current_alarm = None
                elif value == "VJOURNAL":
                    current_context = "VCALENDAR"
                continue

            # Context Parsing
            if current_context == "VJOURNAL":
                if key == "UID": data["uid"] = value
                elif key == "DTSTAMP": data["dtstamp"] = parse_dt(value)
                elif key == "SUMMARY": data["summary"] = value
                elif key == "DESCRIPTION": 
                    data["description"] = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
                elif key == "DTSTART": data["dtstart"] = parse_dt(value)
                elif key == "STATUS": data["status"] = value
                elif key == "CLASS": data["classification"] = value
                elif key == "SEQUENCE": data["sequence"] = int(value)
                elif key == "ORGANIZER":
                    if value.lower().startswith("mailto:"):
                        data["organizer_email"] = value[7:]
                    else:
                        data["organizer_email"] = value
                    data["organizer_name"] = params.get("CN")
                elif key == "CATEGORIES":
                    # Naive split, real world might need to differentiate tags if convention exists
                    cats = value.split(",")
                    data["categories"].extend(cats)
                elif key == "RELATED-TO": data["related_to"] = value
                elif key == "URL": data["url"] = value
                elif key == "RRULE":
                    r_parts = value.split(";")
                    r_data = {}
                    for rp in r_parts:
                        if "=" not in rp: continue
                        k, v = rp.split("=")
                        if k == "FREQ": r_data["frequency"] = v
                        elif k == "INTERVAL": r_data["interval"] = int(v)
                        elif k == "COUNT": r_data["count"] = int(v)
                        elif k == "UNTIL": r_data["until"] = parse_dt(v)
                    if "frequency" in r_data:
                        data["recurrence_rule"] = RecurrenceRule(**r_data)
                elif key == "ATTACH":
                    # Basic handling for URL attachments
                    mime = params.get("FMTTYPE", "application/octet-stream")
                    # Try to derive a filename from URL or default
                    fname = "attachment"
                    if "/" in value:
                        fname = value.split("/")[-1]
                    data["attachments"].append(Attachment(
                        filename=fname,
                        mime_type=mime,
                        url=value
                    ))

            elif current_context == "VALARM":
                if key == "ACTION": current_alarm["action"] = value
                elif key == "DESCRIPTION": current_alarm["description"] = value
                elif key == "TRIGGER":
                    val_clean = "".join(c for c in value if c.isdigit())
                    if val_clean:
                         current_alarm["trigger_minutes"] = int(val_clean)

        return cls(**data)

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
    TEST_VJOURNAL_SIMPLE = """BEGIN:VCALENDAR
BEGIN:VJOURNAL
UID:journal-simple
SUMMARY:Dear Diary
DESCRIPTION:Today was a good day.
DTSTART:20260105T183000Z
END:VJOURNAL
END:VCALENDAR"""

    TEST_VJOURNAL_COMPLEX = """BEGIN:VCALENDAR
BEGIN:VJOURNAL
UID:journal-complex
DTSTAMP:20260105T190000Z
SUMMARY:Project Notes
DESCRIPTION:Discussion points:\\n1. Architecture\\n2. 
 Deserialization logic
STATUS:FINAL
CLASS:PRIVATE
CATEGORIES:WORK,MEETING
ATTACH;FMTTYPE=application/pdf:http://example.com/specs.pdf
END:VJOURNAL
END:VCALENDAR"""

    print("--- Testing Deserialization (Simple) ---")
    j = VJournal.from_vcalendar_string(TEST_VJOURNAL_SIMPLE)
    print(f"Parsed Summary: {j.summary}")
    print(f"Parsed Start: {j.dtstart}")
    if j.summary == "Dear Diary":
        print("[PASS] Simple VJournal parsed.")
    else:
        print("[FAIL] Simple parsing mismatch.")

    print("\n--- Testing Deserialization (Complex) ---")
    jc = VJournal.from_vcalendar_string(TEST_VJOURNAL_COMPLEX)
    print(f"Parsed Description: {jc.description.replace(chr(10), ' ')}")
    print(f"Parsed Status: {jc.status}")
    
    # Check folding and escaping
    if "Deserialization logic" in jc.description and "\n" in jc.description:
        print("[PASS] Description folding and unescaping handled.")
    else:
        print(f"[FAIL] Description issue: {jc.description}")

    if jc.attachments and jc.attachments[0].mime_type == "application/pdf":
        print("[PASS] Attachment parsed.")
        print(f"Attachment URL: {jc.attachments[0].url}")
    else:
        print("[FAIL] Attachment missing or incorrect.")


    # outputs:
    # > --- Testing Deserialization (Simple) ---
    # > Parsed Summary: Dear Diary
    # > Parsed Start: 2026-01-05 18:30:00
    # > [PASS] Simple VJournal parsed.

    # > --- Testing Deserialization (Complex) ---
    # > Parsed Description: Discussion points: 1. Architecture 2. Deserialization logic
    # > Parsed Status: FINAL
    # > [PASS] Description folding and unescaping handled.
    # > [PASS] Attachment parsed.
    # > Attachment URL: http://example.com/specs.pdf

    # > /tmp/ipykernel_35348/2774852803.py:49: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    # > class VJournal(BaseModel):
