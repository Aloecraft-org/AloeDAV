from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

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
    event = VEvent(
        uid="event-123-456@example.com",
        summary="Team Standup Meeting",
        dtstart=datetime(2026, 1, 6, 10, 0, 0),
        dtend=datetime(2026, 1, 6, 10, 30, 0),
        location="Conference Room A",
        description="Daily team standup to sync on progress",
        organizer_name="Alice Johnson",
        organizer_email="alice@example.com",
        status=EventStatus.CONFIRMED,
        transparency=Transparency.OPAQUE,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.DAILY,
            interval=1,
            until=datetime(2026, 3, 31),
        ),
        attendees=[
            Attendee(
                email="bob@example.com",
                name="Bob Smith",
                participation_status="ACCEPTED",
            ),
            Attendee(
                email="charlie@example.com",
                name="Charlie Brown",
                participation_status="TENTATIVE",
            ),
        ],
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=15, description="Reminder"),
        ],
        categories=["WORK", "MEETING"],
    )
    
    print(event.model_dump_json(indent=2))