from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

class TodoStatus(str, Enum):
    NEEDS_ACTION = "NEEDS-ACTION"
    IN_PROCESS = "IN-PROCESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class TodoClass(str, Enum):
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

class Alarm(BaseModel):
    action: str = "DISPLAY"
    trigger_minutes: int = Field(15, description="Minutes before due date")
    description: Optional[str] = None

class Attendee(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: str = "REQ-PARTICIPANT"
    participation_status: str = "NEEDS-ACTION"

class VTodo(BaseModel):
    # Required fields
    uid: str = Field(..., description="Unique identifier")
    summary: str = Field(..., description="Todo title/summary")
    dtstamp: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    
    # Task timing
    dtstart: Optional[datetime] = None
    due: Optional[datetime] = None
    duration: Optional[str] = None  # ISO 8601 duration format
    completed: Optional[datetime] = None
    
    # Task details
    description: Optional[str] = None
    categories: List[str] = []
    comments: Optional[str] = None
    
    # Task properties
    status: TodoStatus = TodoStatus.NEEDS_ACTION
    classification: TodoClass = TodoClass.PUBLIC
    priority: int = 0  # 0 = undefined, 1-4 = high, 5 = medium, 6-9 = low
    percent_complete: int = Field(0, ge=0, le=100)
    sequence: int = 0
    
    # Organizer and attendees
    organizer_name: Optional[str] = None
    organizer_email: Optional[EmailStr] = None
    attendees: List[Attendee] = []
    
    # Recurrence
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_id: Optional[datetime] = None
    
    # Notifications
    alarms: List[Alarm] = []
    
    # Metadata
    url: Optional[str] = None
    location: Optional[str] = None
    version: str = "2.0"
    
    class Config:
        use_enum_values = True


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
        lines.append(f"STATUS:{self.status}")
        lines.append(f"CLASS:{self.classification}")
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
    todo = VTodo(
        uid="todo-789-012@example.com",
        summary="Prepare quarterly report",
        dtstart=datetime(2026, 1, 6, 9, 0, 0),
        due=datetime(2026, 1, 15, 17, 0, 0),
        description="Compile Q4 metrics and analysis for stakeholder presentation",
        status=TodoStatus.IN_PROCESS,
        priority=2,
        percent_complete=45,
        organizer_name="Alice Johnson",
        organizer_email="alice@example.com",
        attendees=[
            Attendee(
                email="david@example.com",
                name="David Lee",
                role="REQ-PARTICIPANT",
                participation_status="ACCEPTED",
            ),
        ],
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=1440, description="Due tomorrow"),
            Alarm(action="DISPLAY", trigger_minutes=60, description="Due in 1 hour"),
        ],
        categories=["WORK", "REPORTING"],
        location="Office",
    )
    
    print(todo.model_dump_json(indent=2))
    
    # Example of a completed recurring task
    recurring_todo = VTodo(
        uid="todo-recurring@example.com",
        summary="Weekly code review",
        dtstart=datetime(2026, 1, 6, 14, 0, 0),
        due=datetime(2026, 1, 9, 17, 0, 0),
        status=TodoStatus.COMPLETED,
        completed=datetime(2026, 1, 9, 16, 30, 0),
        percent_complete=100,
        priority=3,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.WEEKLY,
            interval=1,
        ),
        categories=["WORK", "DEVELOPMENT"],
    )
    
    print("\n")
    print(recurring_todo.model_dump_json(indent=2))