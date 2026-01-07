# model/vcard.py

import uuid
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from aloedav.model.m00_constant import PhoneType, AddressType
from aloedav.model.m01_base import Address, Phone
from aloedav.model import ModelUtil

class VCard(BaseModel):
    # Required fields
    full_name: str = Field(..., alias="fn")
    extended_attributes: Optional[dict[str, str]] = Field(default_factory=dict)
    given_name: Optional[str] = None
    family_name: Optional[str] = None

    # Contact information
    emails: Optional[list[str]] = []
    phones: Optional[list[Phone]] = []
    addresses: Optional[list[Address]] = []
    
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

    @classmethod
    def from_vcard_string(cls, vcard_string: str) -> "VCard":
        lines = ModelUtil.unfold_lines(vcard_string)
        data = {
            "fn": None,
            "emails": [],
            "phones": [],
            "addresses": [],
            "categories": [],
        }

        for line in lines:
            if ":" not in line: continue
            key_part, value = line.split(":", 1)
            
            # Parse params (KEY;PARAM=VAL:VALUE)
            params = {}
            if ";" in key_part:
                parts = key_part.split(";")
                key = parts[0].upper()
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        params[k.upper()] = v
                    else:
                        params[p.upper()] = True
            else:
                key = key_part.upper()

            if key == "FN":
                data["fn"] = value
            elif key == "N":
                # Family;Given;Middle;Prefix;Suffix
                parts = value.split(";")
                if len(parts) >= 1: data["family_name"] = parts[0]
                if len(parts) >= 2: data["given_name"] = parts[1]
            elif key == "EMAIL":
                data["emails"].append(value)
            elif key == "TEL":
                # Naive mapping of TYPE param to Enum
                p_type = params.get("TYPE", "").upper()
                type_enum = None
                for t in PhoneType:
                    if t.value.upper() in p_type:
                        type_enum = t
                        break
                is_pref = "PREF" in p_type.split(',')
                data["phones"].append(Phone(number=value, type=type_enum, is_preferred=is_pref))
            elif key == "ADR":
                # ;;Street;City;State;Zip;Country
                parts = value.split(";")
                parts.extend([""] * (7 - len(parts))) # Ensure length
                
                addr_type = None
                p_type = params.get("TYPE", "").upper()
                if "WORK" in p_type: addr_type = AddressType.WORK
                elif "HOME" in p_type: addr_type = AddressType.HOME
                elif "POSTAL" in p_type: addr_type = AddressType.POSTAL
                elif "PARCEL" in p_type: addr_type = AddressType.PARCEL

                data["addresses"].append(Address(
                    street=parts[2],
                    city=parts[3],
                    state=parts[4],
                    postal_code=parts[5],
                    country=parts[6],
                    type=addr_type
                ))
            elif key == "ORG":
                data["organization"] = value
            elif key == "TITLE":
                data["job_title"] = value
            elif key == "NOTE":
                data["notes"] = value
            elif key == "URL":
                data["url"] = value
            elif key == "UID":
                data["uid"] = value
            elif key == "CATEGORIES":
                data["categories"].extend(value.split(","))
            elif key.startswith("X-"):
                if "extended_attributes" not in data: data["extended_attributes"] = {}
                data["extended_attributes"][key] = value

        if not data["fn"]: data["fn"] = "Unknown"
        
        return cls(**data)

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

        # Ensure UID exists
        if not self.uid:
            self.uid = str(uuid.uuid4())
        lines.append(f"UID:{self.uid}")

        lines.append("END:VCARD")
        return "\r\n".join(lines)


# Example usage
if __name__ == "__main__":
    import sys
    import os
    
    # Try to import testdata
    try:
        from aloedav import testdata
        print("--- Loaded Test Data ---")
    except ImportError:
        print("Warning: Could not import testdata. Using mock data.")
        class MockData:
            TEST_VCARD_FOLDED = """BEGIN:VCARD
VERSION:3.0
FN:Mock Turtle
NOTE:This is a test of folding
  lines.
END:VCARD"""
        testdata = MockData()

    print("\n--- Testing Deserialization (Simple) ---")
    if hasattr(testdata, 'TEST_VCARD_SIMPLE'):
        v = VCard.from_vcard_string(testdata.TEST_VCARD_SIMPLE)
        print(f"Parsed FN: {v.full_name}")
        print(f"Parsed Email: {v.emails[0] if v.emails else 'None'}")
        if v.full_name == "Forrest Gump": print("[PASS] Simple vCard parsed.")
        else: print("[FAIL] Simple parsing mismatch.")

    print("\n--- Testing Deserialization (Folded) ---")
    v_folded = VCard.from_vcard_string(testdata.TEST_VCARD_FOLDED)
    print(f"Parsed FN: {v_folded.full_name}")
    print(f"Parsed Note: {v_folded.notes[:50]}..." if v_folded.notes else "No Notes")
    
    # Check if folding was handled (no newlines in note)
    if v_folded.notes and "\n" not in v_folded.notes and "test the unfolding" in v_folded.notes:
        print("[PASS] Folded lines merged correctly in Deserialization.")
    elif "test of folding lines" in (v_folded.notes or ""): # Fallback for mock data check
        print("[PASS] Mock folded lines merged.")
    else:
        print("[FAIL] Folding check failed.")

    # outputs:

    # > Parsed FN: Forrest Gump
    # > Parsed Email: forrestgump@example.com
    # > [PASS] Simple vCard parsed.
    # > 
    # > --- Testing Deserialization (Folded) ---
    # > Parsed FN: Folded Line Tester
    # > Parsed Note: This is a long note that is folded over multiple l...
    # > [PASS] Folded lines merged correctly in Deserialization.