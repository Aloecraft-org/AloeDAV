from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import StrEnum
from aloedav.model import ModelUtil
from aloedav.model.m00_constant import TodoClass, TodoStatus
from aloedav.model.m01_base import RecurrenceRule, Alarm, Attendee

class VTodo(BaseModel):
    # Required fields
    uid: str = Field(..., description="Unique identifier")
    summary: str = Field(..., description="Todo title/summary")
    dtstamp: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    
    # Task timing
    dtstart: Optional[datetime] = None
    due: Optional[datetime] = None
    duration: Optional[str] = None  # ISO 8601 duration format
    completed: Optional[datetime] = None
    
    # Task details
    description: Optional[str] = None
    categories: Optional[List[str]] = []
    comments: Optional[str] = None
    
    # Task properties
    status: Optional[TodoStatus] = TodoStatus.NEEDS_ACTION
    classification: Optional[TodoClass] = TodoClass.PUBLIC
    priority: Optional[int] = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    percent_complete: Optional[int] = Field(0, ge=0, le=100)
    sequence: Optional[int] = 0
    
    # Organizer and attendees
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    attendees: Optional[List[Attendee]] = []
    
    # Recurrence
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    
    # Notifications
    alarms: Optional[List[Alarm]] = []
    
    # Metadata
    url: Optional[str] = None
    location: Optional[str] = None
    version: Optional[str] = "2.0"
    
    class Config:
        use_enum_values = True

    @classmethod
    def from_vcalendar_string(cls, ics_string: str) -> "VTodo":
        lines = ModelUtil.unfold_lines(ics_string)
        data = {
            "attendees": [],
            "alarms": [],
            "categories": [],
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
                elif value == "VTODO":
                    current_context = "VTODO"
                elif value == "VALARM":
                    current_context = "VALARM"
                    current_alarm = {"trigger_minutes": 15} # default
                continue
            elif key == "END":
                if value == "VALARM":
                    if current_alarm:
                        data["alarms"].append(Alarm(**current_alarm))
                    current_context = "VTODO"
                    current_alarm = None
                elif value == "VTODO":
                    current_context = "VCALENDAR"
                continue

            # Parsing properties based on context
            if current_context == "VTODO":
                if key == "UID": data["uid"] = value
                elif key == "SUMMARY": data["summary"] = value
                elif key == "DTSTART": data["dtstart"] = parse_dt(value)
                elif key == "DTSTAMP": data["dtstamp"] = parse_dt(value)
                elif key == "DUE": data["due"] = parse_dt(value)
                elif key == "COMPLETED": data["completed"] = parse_dt(value)
                elif key == "DURATION": data["duration"] = value
                elif key == "DESCRIPTION": 
                    data["description"] = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
                elif key == "LOCATION": data["location"] = value
                elif key == "STATUS": data["status"] = value
                elif key == "CLASS": data["classification"] = value
                elif key == "SEQUENCE": data["sequence"] = int(value)
                elif key == "PRIORITY": data["priority"] = int(value)
                elif key == "PERCENT-COMPLETE": data["percent_complete"] = int(value)
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
                    val_clean = "".join(c for c in value if c.isdigit())
                    if val_clean:
                         current_alarm["trigger_minutes"] = int(val_clean)

        return cls(**data)

    def to_vcalendar_string(self) -> str:
        """
        Serializes the task into a valid iCalendar (ICS) string with a VTODO component.
        """

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Vera//aloecraft.org//",
            "BEGIN:VTODO"
        ]

        def format_dt(dt: datetime) -> str:
            # iCalendar format: YYYYMMDDTHHMMSS
            return dt.strftime("%Y%m%dT%H%M%S")

        # --- Core Properties ---
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
            lines.append("BEGIN:VALARM")
            lines.append(f"ACTION:{alarm.action}")
            # Format trigger as negative ISO duration (e.g., -PT15M)
            lines.append(f"TRIGGER:-PT{alarm.trigger_minutes}M")
            
            desc = alarm.description if alarm.description else self.summary
            lines.append(f"DESCRIPTION:{desc}")
            lines.append("END:VALARM")

        lines.append("END:VTODO")
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)

# Example usage
if __name__ == "__main__":
    # Mock Data for VTodo deserialization test
    TEST_VTODO_SIMPLE = """BEGIN:VCALENDAR
BEGIN:VTODO
UID:todo-simple
SUMMARY:Buy Milk
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR"""

    TEST_VTODO_COMPLEX = """BEGIN:VCALENDAR
BEGIN:VTODO
UID:todo-complex
SUMMARY:Project Deadline
DESCRIPTION:Complete the full refactor of the 
 codebase including deserialization.
STATUS:IN-PROCESS
PERCENT-COMPLETE:45
DUE:20260120T170000Z
CATEGORIES:WORK,URGENT
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT15M
DESCRIPTION:Deadline approaching
END:VALARM
END:VTODO
END:VCALENDAR"""

    print("--- Testing Deserialization (Simple) ---")
    todo = VTodo.from_vcalendar_string(TEST_VTODO_SIMPLE)
    print(f"Parsed Summary: {todo.summary}")
    print(f"Parsed Status: {todo.status}")
    if todo.summary == "Buy Milk" and todo.status == TodoStatus.NEEDS_ACTION:
        print("[PASS] Simple VTodo parsed.")
    else:
        print("[FAIL] Simple parsing mismatch.")

    print("\n--- Testing Deserialization (Complex) ---")
    todo_c = VTodo.from_vcalendar_string(TEST_VTODO_COMPLEX)
    print(f"Parsed Summary: {todo_c.summary}")
    print(f"Parsed Description: {todo_c.description.replace(chr(10), ' ')}")
    print(f"Parsed Due: {todo_c.due}")
    
    # Check folding logic (newline in description should be removed/merged)
    if "refactor of the codebase" in todo_c.description:
        print("[PASS] Folding handled.")
    else:
        print(f"[FAIL] Description folding issue: '{todo_c.description}'")

    if len(todo_c.alarms) == 1 and todo_c.alarms[0].trigger_minutes == 15:
        print("[PASS] Alarm parsed.")
    else:
        print("[FAIL] Alarm parsing issue.")

    # outputs:

    # > --- Testing Deserialization (Simple) ---
    # > Parsed Summary: Buy Milk
    # > Parsed Status: NEEDS-ACTION
    # > [PASS] Simple VTodo parsed.
    # > 
    # > --- Testing Deserialization (Complex) ---
    # > Parsed Summary: Project Deadline
    # > Parsed Description: Complete the full refactor of the codebase including deserialization.
    # > Parsed Due: 2026-01-20 17:00:00
    # > [PASS] Folding handled.
    # > [PASS] Alarm parsed.
    # > 
    # > /tmp/ipykernel_35348/4270628224.py:44: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    # >   class VTodo(BaseModel):
