from enum import StrEnum, Flag, auto

class AlarmAction(StrEnum):
    DISPLAY = "DISPLAY"
    AUDIO = "AUDIO"
    EMAIL = "EMAIL"
    PROCEDURE = "PROCEDURE"

class RecurrenceFrequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"

class PhoneType(StrEnum):
    VOICE = "voice"
    FAX = "fax"
    MESSAGE = "message"
    CELL = "cell"
    VIDEO = "video"
    PAGER = "pager"
    TEXT = "text"
    WORK = "work"

class AddressType(StrEnum):
    HOME = "home"
    WORK = "work"
    POSTAL = "postal"
    PARCEL = "parcel"

class EventStatus(StrEnum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

class EventClass(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    CONFIDENTIAL = "CONFIDENTIAL"

class Transparency(StrEnum):
    OPAQUE = "OPAQUE"  # Busy
    TRANSPARENT = "TRANSPARENT"  # Free

class JournalStatus(StrEnum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    CANCELLED = "CANCELLED"

class JournalClass(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    CONFIDENTIAL = "CONFIDENTIAL"

class TodoStatus(StrEnum):
    NEEDS_ACTION = "NEEDS-ACTION"
    IN_PROCESS = "IN-PROCESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class TodoClass(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    CONFIDENTIAL = "CONFIDENTIAL"

class CalendarComponents(Flag):
    INVALID=0
    VEVENT=auto()
    VJOURNAL=auto()
    VTODO=auto()