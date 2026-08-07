import re
from aloedav.exceptions import PreconditionFailed, WebDAVError, AuthenticationError, ResourceNotFound, AloeDAVClientError
from aloedav.model.m00_constant import EventStatus, Transparency
from aloedav.model.m00_constant import PhoneType, AddressType
# from aloedav.model.m01_base import Address, Phone, Attendee, RecurrenceRule, Attachment
from aloedav.model import ModelUtil
from aloedav.model.m02_vcard import VCARD
from aloedav.model.m02_vevent import VEVENT
from aloedav.model.m02_vtodo import VTODO
from aloedav.model.m02_vjournal import VJOURNAL


def parse_dt(val):
    """
    Parses a DATE-TIME (YYYYMMDDTHHMMSS[Z]) or a DATE (YYYYMMDD) per RFC 5545 3.3.4/3.3.5.

    A trailing 'Z' yields an aware UTC datetime; without it the value is floating
    local time and stays naive. A DATE is anchored at midnight. Values that match
    neither form return None rather than a fabricated timestamp -- silently
    substituting "now" turns an unparseable date into a plausible wrong one.
    """
    from datetime import datetime, timezone

    if not val:
        return None

    val = str(val).strip()
    is_utc = val.endswith("Z")
    if is_utc:
        val = val[:-1]

    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(val, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc) if is_utc else parsed

    return None

def _split_unquoted(text:str, delimiter:str, maxsplit:int=-1)-> list[str]:
    """
    Splits on delimiters that are neither backslash-escaped nor inside a quoted
    parameter value. RFC 5545 3.2 allows ';' and ':' inside a DQUOTE-delimited
    parameter value, so a naive split corrupts lines like CN="Doe; Jane".
    """
    parts, buf, in_quote, i = [], [], False, 0
    while i < len(text):
        char = text[i]
        if char == '\\' and i + 1 < len(text):
            buf.append(char)
            buf.append(text[i + 1])
            i += 2
            continue
        if char == '"':
            in_quote = not in_quote
        elif char == delimiter and not in_quote and maxsplit != 0:
            parts.append(''.join(buf))
            buf = []
            maxsplit -= 1
            i += 1
            continue
        buf.append(char)
        i += 1
    parts.append(''.join(buf))
    return parts

def _decompose_line(line:str)-> tuple[str,dict,str]:
    """
    returns (key, params_dict, value)
    """
    segments = _split_unquoted(line, ":", maxsplit=1)
    key_part = segments[0]
    value = segments[1] if len(segments) > 1 else ""
    params = {} # Extract params (KEY;PARAM=VAL:VALUE)
    if ";" in key_part:
        parts = _split_unquoted(key_part, ";")
        key = parts[0].upper()
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.upper()
                v = _unquote_param(v)
                # vCard 3.0 repeats the parameter rather than comma-joining it
                # (TYPE=CELL;TYPE=PREF), so repeats accumulate instead of
                # overwriting -- otherwise only the last type survives.
                params[k] = f"{params[k]},{v}" if k in params and params[k] is not True else v
            else:
                params[p.upper()] = True
    else:
        key = key_part.upper()
    return key, params, value

def _unquote_param(value:str)-> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value.replace("\\;", ";").replace("\\,", ",")

def _init_data_dict(data:dict, context:str)->dict:
    if not "context" in data:
        data["context"] = context
    assert data["context"] == context, f"_init_data_dict for {context} (context is: {data["context"]})"

    if not "unknown_attributes" in data:
        data["unknown_attributes"] = []

    match context:
        case "ROOT":
            if not "content" in data:
                data["content"] = {}
                data["raw_contents"] = None
        case "VCARD":
            if not "extended_attributes" in data:
                data["extended_attributes"] = {}
            if not "fn" in data:
                data["fn"] = "(unknown)"
            if not "emails" in data:
                data["emails"] = []
            if not "phones" in data:
                data["phones"] = []
            if not "addresses" in data:
                data["addresses"] = []
            if not "categories" in data:
                data["categories"] = []
            if not "prod_id" in data:
                data["prod_id"] = None
            if not "version" in data:
                data["version"] = "3.0"
        case "VCALENDAR":
            if not "extended_attributes" in data:
                data["extended_attributes"] = {}
            if not "items" in data:
                data["items"] = []
            if not "prod_id" in data:
                data["prod_id"] = None
            if not "version" in data:
                data["version"] = "2.0"
        case "VTODO":
            if not "extended_attributes" in data:
                data["extended_attributes"] = {}
            if not "attendees" in data:
                data["attendees"] = []
            if not "alarms" in data:
                data["alarms"] = []
            if not "categories" in data:
                data["categories"] = []
            if not "attachments" in data:
                data["attachments"] = []
        case "VEVENT":
            if not "extended_attributes" in data:
                data["extended_attributes"] = {}
            if not "attendees" in data:
                data["attendees"] = []
            if not "alarms" in data:
                data["alarms"] = []
            if not "categories" in data:
                data["categories"] = []
            if not "attachments" in data:
                data["attachments"] = []
        case "VJOURNAL":
            if not "extended_attributes" in data:
                data["extended_attributes"] = {}
            if not "alarms" in data:
                data["alarms"] = []
            if not "categories" in data:
                data["categories"] = []
            if not "attachments" in data:
                data["attachments"] = []
            if not "tags" in data:
                data["tags"] = []
        case "VALARM":
            if not "action" in data:
                data["action"] = None
            if not "description" in data:
                data["description"] = None
            if not "trigger_minutes" in data:
                data["trigger_minutes"] = 15
    return data

def _context_alarm(data:dict, key:str, params:dict, value:str)->dict:
    match key:
        case "ACTION":
            data["action"] = value
        case "DESCRIPTION":
            data["description"] = value
        case "TRIGGER":
            # Simple parse for standard -PT15M format
            # Removes P, T, M, and - characters to get raw minutes
            val_clean = "".join(c for c in value if c.isdigit())
            if val_clean:
                data["trigger_minutes"] = int(val_clean)
        case _:
            data["unknown_attributes"].append((key, params, value))
    return data

def _context_item(data:dict, key:str, params:dict, value:str)->dict:
    if key.startswith("X-"):
        data["extended_attributes"][key] = value

    elif key == "VERSION": data["version"] = value
    elif key == "PRODID": data["prod_id"] = value
    elif key == "REV": data["rev"] = value
    elif key == "UID": data["uid"] = value
    elif key == "SUMMARY": data["summary"] = ModelUtil.unescape_text(value)
    elif key == "DURATION": data["duration"] = value
    elif key == "LOCATION": data["location"] = ModelUtil.unescape_text(value)
    elif key == "STATUS": data["status"] = value
    elif key == "CLASS": data["classification"] = value
    elif key == "DESCRIPTION":
        data["description"] = ModelUtil.unescape_text(value)
    elif key == "DTSTART": data["dtstart"] = parse_dt(value)
    elif key == "DTEND": data["dtend"] = parse_dt(value)
    elif key == "DTSTAMP": data["dtstamp"] = parse_dt(value)
    elif key == "DUE": data["due"] = parse_dt(value)
    elif key == "COMPLETED": data["completed"] = parse_dt(value)
    elif key == "SEQUENCE": data["sequence"] = int(value)
    elif key == "PRIORITY": data["priority"] = int(value)
    elif key == "PERCENT-COMPLETE": data["percent_complete"] = int(value)
    elif key == "RELATED-TO": data["related_to"] = value
    elif key == "URL": data["url"] = value
    elif key == "TRANSP": data["transparency"] = value
    elif key == "CATEGORIES":
        data["categories"].extend(ModelUtil.split_escaped(value, ","))
    elif key == "ORG":
        data["organization"] = ModelUtil.unescape_text(value)
    elif key == "TITLE":
        data["job_title"] = ModelUtil.unescape_text(value)
    elif key == "NOTE":
        data["notes"] = ModelUtil.unescape_text(value)
    elif key == "FN":
        data["fn"] = ModelUtil.unescape_text(value)
    elif key == "N":
        # Family;Given;Middle;Prefix;Suffix
        parts = ModelUtil.split_escaped(value, ";")
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
        data["phones"].append({
            "number":value,
            "type":type_enum, 
            "is_preferred":is_pref
        })
    elif key == "ADR":
        # PoBox;Ext;Street;City;State;Zip;Country
        parts = ModelUtil.split_escaped(value, ";")
        parts.extend([""] * (7 - len(parts))) # Ensure length
        
        addr_type = None
        p_type = params.get("TYPE", "").upper()
        if "WORK" in p_type: addr_type = AddressType.WORK
        elif "HOME" in p_type: addr_type = AddressType.HOME
        elif "POSTAL" in p_type: addr_type = AddressType.POSTAL
        elif "PARCEL" in p_type: addr_type = AddressType.PARCEL
        data["addresses"].append({
            "street":parts[2],
            "city":parts[3],
            "state":parts[4],
            "postal_code":parts[5],
            "country":parts[6],
            "type":addr_type
        })
    elif key == "ORGANIZER":
        if value.lower().startswith("mailto:"):
            data["organizer_email"] = value[7:]
        else:
            data["organizer_email"] = value
        data["organizer_name"] = params.get("CN")
    elif key == "ATTENDEE":
        email = value[7:] if value.lower().startswith("mailto:") else value
        name = params.get("CN")
        role = params.get("ROLE", "REQ-PARTICIPANT")
        partstat = params.get("PARTSTAT", "NEEDS-ACTION")
        data["attendees"].append({
            "email":email, 
            "name":name, 
            "role":role, 
            "participation_status":partstat
        })
    elif key == "RRULE":
        r_parts = value.split(";")
        r_data = {}
        for rp in r_parts:
            if "=" not in rp: continue
            k, v = rp.split("=")
            if k == "FREQ": r_data["frequency"] = v
            elif k == "INTERVAL": r_data["interval"] = int(v)
            elif k == "COUNT": r_data["count"] = int(v)
            elif k == "UNTIL": r_data["until"] = parse_dt(v)
        if "frequency" in r_data:
            data["recurrence_rule"] = r_data
    elif key == "ATTACH":
        # Basic handling for URL attachments
        mime = params.get("FMTTYPE", "application/octet-stream")
        # Try to derive a filename from URL or default
        fname = "attachment"
        if "/" in value:
            fname = value.split("/")[-1]
        data["attachments"].append({
            "filename":fname,
            "mime_type":mime,
            "url":value
        })
    return data

def webdav_data(contents:str)->dict:
    from aloedav.model.m01_base import VCalendar, Alarm, Attendee, RecurrenceRule, Attachment

    lines = ModelUtil.unfold_lines(contents)
    context = [_init_data_dict({}, "ROOT")]

    context[0]["raw_contents"] = contents

    for line in lines:
        current_context = context[-1]
        if ":" not in line: continue
        key, params, value = _decompose_line(line)
        
        if key == "BEGIN":
            if value == "VCALENDAR":
                assert current_context["context"] == "ROOT", "VCALENDAR must be ROOT element"
                context.append(_init_data_dict({}, "VCALENDAR"))
            elif value == "VCARD":
                assert current_context["context"] == "ROOT", "VCARD must be ROOT element"
                context.append(_init_data_dict({}, "VCARD"))
            elif value == "VTODO":
                assert current_context["context"] == "VCALENDAR", "VTODO must be embedded in VCALENDAR"
                context.append(_init_data_dict({}, "VTODO"))
            elif value == "VEVENT":
                assert current_context["context"] == "VCALENDAR", "VEVENT must be embedded in VCALENDAR"
                context.append(_init_data_dict({}, "VEVENT"))
            elif value == "VJOURNAL":
                assert current_context["context"] == "VCALENDAR", "VJOURNAL must be embedded in VCALENDAR"
                context.append(_init_data_dict({}, "VJOURNAL"))
            elif value == "VALARM":
                assert current_context["context"] != "VALARM", "VALARM not embedded in VALARM"
                context.append(_init_data_dict({}, "VALARM"))
            continue
        elif key == "END":
            assert current_context["context"] == value.upper(), f"END:{value.upper()} should match current context {current_context["context"]}"
            parent_context = context[-2]
            if value == "VCALENDAR" or value == "VCARD":
                parent_context["content"] = context.pop()
            elif value == "VTODO":
                parent_context["items"].append(context.pop())
            elif value == "VEVENT":
                parent_context["items"].append(context.pop())
            elif value == "VJOURNAL":
                parent_context["items"].append(context.pop())
            elif value == "VALARM" and current_context["context"]:
                parent_context["alarms"].append(context.pop())
            context[-1] = parent_context
        elif current_context["context"] == "VALARM":
            current_context = _context_alarm(current_context, key, params, value)
            context[-1] = current_context
        else:
            current_context = _context_item(current_context, key, params, value)
            context[-1] = current_context

    return context[0]

def to_model(data, etag:str=None)->list[VCARD|VTODO|VJOURNAL|VEVENT]:
    data_dict = data if isinstance(data, dict) else webdav_data(data)

    if data_dict["content"]["context"] == "VCARD":
        vcard = VCARD(**data_dict["content"])
        vcard.raw_contents = data_dict["raw_contents"]
        if etag:
            vcard.etag = etag
        return [vcard]
    elif data_dict["content"]["context"] == "VCALENDAR":
        result = []
        for item in data_dict["content"]["items"]:
            match(item["context"]):
                case "VTODO": 
                    new_item = VTODO(**item)
                    new_item.raw_contents = data_dict["raw_contents"]
                    if etag:
                        new_item.etag = etag
                    result.append(new_item)
                case "VJOURNAL": 
                    new_item = VJOURNAL(**item)
                    new_item.raw_contents = data_dict["raw_contents"]
                    if etag:
                        new_item.etag = etag
                    result.append(new_item)
                case "VEVENT": 
                    new_item = VEVENT(**item)
                    new_item.raw_contents = data_dict["raw_contents"]
                    if etag:
                        new_item.etag = etag
                    result.append(new_item)
                case _:
                    raise WebDAVError(f"Unknown element type: {item["context"]}")
        return result
    else:
        raise WebDAVError(f"Unknown element type: {data_dict["content"]["context"]}")