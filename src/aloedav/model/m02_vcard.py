from uuid import uuid4

from pydantic import Field, EmailStr
from typing import Optional

from aloedav.model.m01_base import Item, Address, Phone

class VCARD(Item):
    file_ext:str = "vcf"
    version: str = "3.0"

    full_name: str = Field(..., alias="fn")
    given_name: Optional[str] = None
    family_name: Optional[str] = None

    emails: Optional[list[EmailStr]] = None
    phones: Optional[list[Phone]] = None
    addresses: Optional[list[Address]] = None

    organization: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    nickname: Optional[str] = None
    notes: Optional[str] = None

    def update(self, update:"VCARD"):
        super().update(update)

        if update.full_name:
            self.full_name = update.full_name
        if update.given_name:
            self.given_name = update.given_name
        if update.family_name:
            self.family_name = update.family_name

        if update.emails != None:
            # Empty List is valid input. None means ignore
            self.emails = update.emails
        if update.phones != None:
            # Empty List is valid input. None means ignore
            self.phones = update.phones
        if update.addresses != None:
            # Empty List is valid input. None means ignore
            self.addresses = update.addresses

        if update.organization:
            self.organization = update.organization
        if update.job_title:
            self.job_title = update.job_title
        if update.department:
            self.department = update.department
        if update.nickname:
            self.nickname = update.nickname
        if update.notes:
            self.notes = update.notes