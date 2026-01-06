from pydantic import BaseModel
from enum import StrEnum

# MIKE: Unused Class
class AddressBook(BaseModel):
    href:str
    color:str
    display_name:str
    description:str
