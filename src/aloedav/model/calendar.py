from pydantic import BaseModel
from enum import Flag, auto

class CalendarComponents(Flag):
    INVALID=0
    VEVENT=auto()
    VJOURNAL=auto()
    VTODO=auto()

class Calendar(BaseModel):
    href:str
    color:str
    display_name:str
    description:str
    components:CalendarComponents