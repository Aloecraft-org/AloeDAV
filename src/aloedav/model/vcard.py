# model/vcard.py

import uuid
from pydantic import BaseModel, Field, EmailStr, HttpUrl
from typing import Optional, List
from enum import Enum

class PhoneType(str, Enum):
    VOICE = "voice"
    FAX = "fax"
    MESSAGE = "message"
    CELL = "cell"
    VIDEO = "video"
    PAGER = "pager"
    TEXT = "text"
    WORK = "work"

class AddressType(str, Enum):
    HOME = "home"
    WORK = "work"
    POSTAL = "postal"
    PARCEL = "parcel"

class Phone(BaseModel):
    number: str
    type: Optional[PhoneType] = None
    is_preferred: bool = False

class Address(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    type: Optional[AddressType] = None

class VCard(BaseModel):
    # Required fields
    full_name: str = Field(..., alias="fn")
    given_name: Optional[str] = None
    family_name: Optional[str] = None

    # Contact information
    emails: List[EmailStr] = []
    phones: List[Phone] = []
    addresses: List[Address] = []
    
    # Optional fields
    categories: Optional[list[str]] = None
    organization: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    nickname: Optional[str] = None
    url: Optional[HttpUrl] = None
    notes: Optional[str] = None
    
    # Additional metadata
    version: str = "3.0"
    uid: Optional[str] = None
    
    class Config:
        use_enum_values = True

    def to_vcard_string(self) -> str:
        from datetime import datetime

        # vCard doesn't have an outer "Container". The VCARD itself is the unit.
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            "PRODID:-//Vera//aloecraft.org//",
            # REV is crucial for CardDAV sync to know which version is newer
            f"REV:{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}" 
        ]
        
        # Name
        lines.append(f"FN:{self.full_name}")
        lines.append(f"N:{self.family_name or ''};{self.given_name or ''};;;")
        
        if self.organization:
            lines.append(f"ORG:{self.organization}")
        if self.job_title:
            lines.append(f"TITLE:{self.job_title}")
        
        # Emails
        for email in self.emails:
            lines.append(f"EMAIL;TYPE=INTERNET:{email}")
            
        # Phones
        for phone in self.phones:
            type_str = f";TYPE={phone.type}" if phone.type else ""
            pref_str = ";TYPE=PREF" if phone.is_preferred else ""
            lines.append(f"TEL{type_str}{pref_str}:{phone.number}")

        # Addresses
        for addr in self.addresses:
            type_str = f";TYPE={addr.type}" if addr.type else ""
            # ADR format: ;;street;city;region;code;country
            lines.append(f"ADR{type_str}:;;{addr.street or ''};{addr.city or ''};"
                        f"{addr.state or ''};{addr.postal_code or ''};{addr.country or ''}")

        if self.url:
            lines.append(f"URL:{self.url}")
        if self.notes:
            lines.append(f"NOTE:{self.notes}")

        if self.categories:
            lines.append(f"CATEGORIES:{','.join([self.categories])}")
            
        # Ensure UID exists
        if not self.uid:
            self.uid = str(uuid.uuid4())
        lines.append(f"UID:{self.uid}")

        lines.append("END:VCARD")
        return "\r\n".join(lines)


# Example usage
if __name__ == "__main__":
    vcard = VCard(
        fn="John Doe",
        given_name="John",
        family_name="Doe",
        categories=['someone', 'human'],
        emails=["john.doe@example.com"],
        phones=[
            Phone(number="+1-555-123-4567", type=PhoneType.CELL, is_preferred=True),
            Phone(number="+1-555-987-6543", type=PhoneType.WORK),
        ],
        addresses=[
            Address(
                street="123 Main St",
                city="Springfield",
                state="IL",
                postal_code="62701",
                country="USA",
                type=AddressType.HOME,
            )
        ],
        organization="Acme Corp",
        job_title="Software Engineer",
        url="https://johndoe.com",
        notes="Primary contact for project X",
    )
    
    print(vcard.model_dump_json(indent=2))

    print(vcard.to_vcard_string())