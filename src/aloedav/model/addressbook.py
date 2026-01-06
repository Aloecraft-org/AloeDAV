from pydantic import BaseModel
from enum import StrEnum

class AddressBook(BaseModel):
    href:str
    color:str
    display_name:str
    description:str
