from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum
from aloedav.model.utils import unfold_lines

class EventStatus(str, Enum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

class EventClass(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    CONFIDENTIAL = "CONFIDENTIAL"

class Transparency(str, Enum):
    OPAQUE = "OPAQUE"  # Busy
    TRANSPARENT = "TRANSPARENT"  # Free

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
    by_hour: Optional[List[int]] = None

class Alarm(BaseModel):
    action: str = "DISPLAY"  # DISPLAY, AUDIO, EMAIL, PROCEDURE
    trigger_minutes: int = Field(15, description="Minutes before event")
    description: Optional[str] = None

class Attendee(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: str = "REQ-PARTICIPANT"  # REQ-PARTICIPANT, OPT-PARTICIPANT, NON-PARTICIPANT, CHAIR
    participation_status: str = "NEEDS-ACTION"  # NEEDS-ACTION, ACCEPTED, DECLINED, TENTATIVE, DELEGATED
    is_organizer: bool = False

class VEvent(BaseModel):
    # Required fields
    uid: Optional[str] = Field(default=None, description="Unique identifier")
    summary: str = Field(..., description="Event title")
    dtstart: datetime = Field(..., description="Event start time")
    dtstamp: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    
    # Optional timing
    dtend: Optional[datetime] = None
    duration: Optional[str] = None  # ISO 8601 duration format, e.g., "PT1H"
    
    # Event details
    description: Optional[str] = None
    location: Optional[str] = None
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    
    # Event properties
    status: EventStatus = EventStatus.CONFIRMED
    classification: EventClass = EventClass.PUBLIC
    transparency: Transparency = Transparency.OPAQUE
    sequence: int = 0
    priority: int = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    
    # Recurrence
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    
    # Attendees and notifications
    attendees: List[Attendee] = []
    alarms: List[Alarm] = []
    
    # Metadata
    url: Optional[str] = None
    categories: List[str] = []
    comments: Optional[str] = None
    
    # Version
    version: str = "2.0"
    
    class Config:
        use_enum_values = True

    @classmethod
    def from_vcalendar_string(cls, ics_string: str) -> "VEvent":
        lines = unfold_lines(ics_string)
        data = {
            "attendees": [],
            "alarms": [],
            "categories": [],
        }
        
        current_context = "ROOT" # ROOT -> VCALENDAR -> VEVENT -> VALARM
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
            
            # Split key/params and value
            key_part, value = line.split(":", 1)
            
            # Extract params
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

            # State Machine transitions
            if key == "BEGIN":
                if value == "VCALENDAR":
                    current_context = "VCALENDAR"
                elif value == "VEVENT":
                    current_context = "VEVENT"
                elif value == "VALARM":
                    current_context = "VALARM"
                    current_alarm = {"trigger_minutes": 15} # default
                continue
            elif key == "END":
                if value == "VALARM":
                    if current_alarm:
                        data["alarms"].append(Alarm(**current_alarm))
                    current_context = "VEVENT"
                    current_alarm = None
                elif value == "VEVENT":
                    current_context = "VCALENDAR"
                continue

            # Parsing properties based on context
            if current_context == "VEVENT":
                if key == "UID": data["uid"] = value
                elif key == "SUMMARY": data["summary"] = value
                elif key == "DTSTART": data["dtstart"] = parse_dt(value)
                elif key == "DTSTAMP": data["dtstamp"] = parse_dt(value)
                elif key == "DTEND": data["dtend"] = parse_dt(value)
                elif key == "DURATION": data["duration"] = value
                elif key == "DESCRIPTION": 
                    data["description"] = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
                elif key == "LOCATION": data["location"] = value
                elif key == "STATUS": data["status"] = value
                elif key == "CLASS": data["classification"] = value
                elif key == "TRANSP": data["transparency"] = value
                elif key == "SEQUENCE": data["sequence"] = int(value)
                elif key == "PRIORITY": data["priority"] = int(value)
                elif key == "CATEGORIES": data["categories"] = value.split(",")
                elif key == "ORGANIZER":
                    if value.lower().startswith("mailto:"):
                        data["organizer_email"] = value[7:]
                    else:
                        data["organizer_email"] = value
                    data["organizer_name"] = params.get("CN")
                elif key == "ATTENDEE":
                    email = value[7:] if value.lower().startswith("mailto:") else value
                    name = params.get("CN")
                    role = params.get("ROLE", "REQ-PARTICIPANT")
                    partstat = params.get("PARTSTAT", "NEEDS-ACTION")
                    data["attendees"].append(Attendee(email=email, name=name, role=role, participation_status=partstat))
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

            elif current_context == "VALARM":
                if key == "ACTION": current_alarm["action"] = value
                elif key == "DESCRIPTION": current_alarm["description"] = value
                elif key == "TRIGGER":
                    # Simple parse for standard -PT15M format
                    # Removes P, T, M, and - characters to get raw minutes
                    val_clean = "".join(c for c in value if c.isdigit())
                    if val_clean:
                         current_alarm["trigger_minutes"] = int(val_clean)

        return cls(**data)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the event into a valid iCalendar (ICS) string.
        """
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Vera//aloecraft.org//",
            "BEGIN:VEVENT"
        ]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            # Note: For robust timezone handling, you would normally check for 
            # tzinfo and append 'Z' for UTC. Here we assume naive = local/floating.
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
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
            
        lines.append(f"STATUS:{self.status}")
        lines.append(f"CLASS:{self.classification}")
        lines.append(f"TRANSP:{self.transparency}")
        lines.append(f"SEQUENCE:{self.sequence}")
        lines.append(f"PRIORITY:{self.priority}")
        
        if self.categories:
            lines.append(f"CATEGORIES:{','.join(self.categories)}")

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
            lines.append("BEGIN:VALARM")
            lines.append(f"ACTION:{alarm.action}")
            # Format trigger as negative ISO duration (e.g., -PT15M)
            lines.append(f"TRIGGER:-PT{alarm.trigger_minutes}M")
            
            desc = alarm.description if alarm.description else self.summary
            lines.append(f"DESCRIPTION:{desc}")
            lines.append("END:VALARM")

        lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)


# Example usage
if __name__ == "__main__":
    import sys
    import os
    
    # Try to import testdata
    try:
        from aloedav import testdata
        print("--- Loaded Test Data ---")
    except ImportError:
        print("Warning: Could not import testdata. Using mock data.")
        class MockData:
            TEST_VEVENT_SIMPLE = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:mock-simple
DTSTART:20260101T120000Z
SUMMARY:Mock Event
END:VEVENT
END:VCALENDAR"""
        testdata = MockData()

    print("\n--- Testing Deserialization (Simple) ---")
    if hasattr(testdata, 'TEST_VEVENT_SIMPLE'):
        ev = VEvent.from_vcalendar_string(testdata.TEST_VEVENT_SIMPLE)
        print(f"Parsed Summary: {ev.summary}")
        print(f"Parsed Start: {ev.dtstart}")
        if ev.summary == "Bastille Day Party": print("[PASS] Simple VEvent parsed.")
        else: print("[FAIL] Simple parsing mismatch.")

    print("\n--- Testing Deserialization (Folded) ---")
    if hasattr(testdata, 'TEST_VEVENT_FOLDED'):
        ev_folded = VEvent.from_vcalendar_string(testdata.TEST_VEVENT_FOLDED)
        print(f"Parsed Summary: {ev_folded.summary}")
        print(f"Parsed Description: {ev_folded.description[:50]}..." if ev_folded.description else "No Desc")
        
        # Check if folding was handled
        if ev_folded.description and "\n" not in ev_folded.description and "legacy backend systems" in ev_folded.description:
            print("[PASS] Folded lines merged correctly in VEvent.")
        else:
            print("[FAIL] Folding check failed.")

        # outputs:

        # > --- Loaded Test Data ---
        # > 
        # > --- Testing Deserialization (Simple) ---
        # > Parsed Summary: Bastille Day Party
        # > Parsed Start: 1997-07-14 17:00:00
        # > [PASS] Simple VEvent parsed.
        # > 
        # > --- Testing Deserialization (Folded) ---
        # > Parsed Summary: Project Planning Meeting
        # > Parsed Description: We will discuss the roadmap for the upcoming quart...
        # > [PASS] Folded lines merged correctly in VEvent.
        # > 
        # > /tmp/ipykernel_35348/1121317153.py:49: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
        # >   class VEvent(BaseModel):