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
    
    @fn.setter
    def fn(self, value):
        self.full_name = value

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
        from aloedav.model import ModelUtil

        esc = ModelUtil.escape_text
        param = ModelUtil.escape_param

        # Ensure UID exists
        if not self.uid:
            self.uid = f"contact-{uuid4()}"

        lines = [
            "BEGIN:VCARD",
            f"VERSION:{self.version}",
            f"PRODID:{esc(self.prod_id)}",
            f"REV:{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
            f"FN:{esc(self.full_name)}",
            f"N:{esc(self.family_name or '')};{esc(self.given_name or '')};;;",
            f"UID:{esc(self.uid)}",
        ]

        if self.organization:
            lines.append(f"ORG:{esc(self.organization)}")
        if self.job_title:
            lines.append(f"TITLE:{esc(self.job_title)}")

        # Emails
        if self.emails:
            for email in self.emails:
                lines.append(f"EMAIL;TYPE=INTERNET:{esc(email)}")

        # Phones
        if self.phones:
            for phone in self.phones:
                p_val = phone.type.value if hasattr(phone.type, 'value') else phone.type
                type_str = f";TYPE={param(p_val)}" if p_val else ""
                pref_str = ";TYPE=PREF" if phone.is_preferred else ""
                lines.append(f"TEL{type_str}{pref_str}:{esc(phone.number)}")

        # Addresses
        if self.addresses:
            for addr in self.addresses:
                a_val = addr.type.value if hasattr(addr.type, 'value') else addr.type
                type_str = f";TYPE={param(a_val)}" if a_val else ""
                # ADR format: pobox;ext;street;city;region;code;country
                components = ";".join(esc(c or '') for c in (
                    "", "", addr.street, addr.city,
                    addr.state, addr.postal_code, addr.country))
                lines.append(f"ADR{type_str}:{components}")

        if self.url:
            lines.append(f"URL:{esc(self.url)}")
        if self.notes:
            lines.append(f"NOTE:{esc(self.notes)}")

        if self.categories:
            lines.append(f"CATEGORIES:{','.join(esc(c) for c in self.categories)}")

        if self.extended_attributes:
            for k, v in self.extended_attributes.items():
                lines.append(f"{k}:{esc(v)}")

        lines.append("END:VCARD")
        return ModelUtil.join_lines(lines)
    
    def to_webdav_string(self) -> str:
        return self.to_vcard_string()