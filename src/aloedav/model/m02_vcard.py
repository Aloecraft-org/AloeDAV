from uuid import uuid4

from pydantic import Field, EmailStr
from typing import Optional

from aloedav.model.m01_base import Item, Address, Phone

class VCARD(Item):
    content_type:str = "text/vcard; charset=utf-8"
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

    @property
    def fn(self):
        return self.full_name

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
    
    def to_vcard_string(self) -> str:
        from uuid import uuid4
        from datetime import datetime, timezone
        lines = [f"""
BEGIN:VCARD
VERSION:{self.version}
PRODID:{self.prod_id}
REV:{datetime.now(timezone.utc()).strftime('%Y-%m-%dT%H:%M:%SZ')}
FN:{self.full_name}
N:{self.family_name or ''};{self.given_name or ''};;;
"""]

        # Ensure UID exists
        if not self.uid:
            self.uid = f"contact-{uuid4()}"
        lines.append(f"UID:{self.uid}")

        if self.organization:
            lines.append(f"ORG:{self.organization}")
        if self.job_title:
            lines.append(f"TITLE:{self.job_title}")
        
        # Emails
        for email in self.emails:
            lines.append(f"EMAIL;TYPE=INTERNET:{email}")
            
        # Phones
        for phone in self.phones:
            p_val = phone.type.value if hasattr(phone.type, 'value') else phone.type
            type_str = f";TYPE={p_val}" if p_val else ""
            pref_str = ";TYPE=PREF" if phone.is_preferred else ""
            lines.append(f"TEL{type_str}{pref_str}:{phone.number}")

        # Addresses
        for addr in self.addresses:
            a_val = addr.type.value if hasattr(addr.type, 'value') else addr.type
            type_str = f";TYPE={a_val}" if a_val else ""
            # ADR format: ;;street;city;region;code;country
            lines.append(f"ADR{type_str}:;;{addr.street or ''};{addr.city or ''};")

        if self.url:
            lines.append(f"URL:{self.url}")
        if self.notes:
            lines.append(f"NOTE:{self.notes}")

        if self.categories:
            lines.append(f"CATEGORIES:{','.join(self.categories)}")
        
        for k, v in self.extended_attributes.items():
            lines.append(f"{k}:{v}")


        lines.append("END:VCARD")
        return "\r\n".join(lines)