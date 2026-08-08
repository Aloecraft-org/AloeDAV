import re
from aloedav.exceptions import PreconditionFailed, WebDAVError, AuthenticationError, ResourceNotFound, AloeDAVClientError, ParseError
from aloedav.model.m00_constant import EventStatus, Transparency
from aloedav.model.m00_constant import PhoneType, AddressType
# from aloedav.model.m01_base import Address, Phone, Attendee, RecurrenceRule, Attachment
from aloedav.model import ModelUtil
from aloedav.model.m00_datetime import DateTimeValue
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
    if data["context"] != context:
        raise ParseError(f"_init_data_dict for {context} (context is: {data['context']})")

    # Properties and sub-components this parser does not model are kept as the
    # verbatim unfolded source lines. Round-tripping them untouched is the only
    # way an editing client can avoid destroying data written by another one.
    if not "unknown_properties" in data:
        data["unknown_properties"] = []
    if not "unknown_components" in data:
        data["unknown_components"] = []

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

def _context_alarm(data:dict, key:str, params:dict, value:str, line:str=None)->dict:
    match key:
        case "ACTION":
            data["action"] = value
        case "DESCRIPTION":
            data["description"] = ModelUtil.unescape_text(value)
        case "TRIGGER":
            # Simple parse for standard -PT15M format
            # Removes P, T, M, and - characters to get raw minutes
            val_clean = "".join(c for c in value if c.isdigit())
            if val_clean:
                data["trigger_minutes"] = int(val_clean)
        case _:
            data["unknown_properties"].append(line if line is not None else f"{key}:{value}")
    return data

def _context_item(data:dict, key:str, params:dict, value:str, line:str=None)->dict:
    if key.startswith("X-"):
        data["extended_attributes"][key] = ModelUtil.unescape_text(value)

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
    elif key == "DTSTART": data["dtstart"] = DateTimeValue.parse(value, params)
    elif key == "DTEND": data["dtend"] = DateTimeValue.parse(value, params)
    # Identifies this component as an override of one instance of a recurring
    # series rather than the series master. Without it the two are
    # indistinguishable and collide on filename.
    elif key == "RECURRENCE-ID": data["recurrence_id"] = DateTimeValue.parse(value, params)
    elif key == "DTSTAMP": data["dtstamp"] = parse_dt(value)
    elif key == "DUE": data["due"] = DateTimeValue.parse(value, params)
    elif key == "COMPLETED": data["completed"] = parse_dt(value)
    elif key in ("EXDATE", "RDATE") and str(params.get("VALUE", "")).upper() != "PERIOD":
        field = key.lower()
        data.setdefault(field, []).extend(DateTimeValue.parse_list(value, params))
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
        from aloedav.model.m01_base import RecurrenceRule
        # Integer-valued BY* parts; BYDAY is textual ("MO", "-1SU") and WKST is
        # a bare weekday, so neither is coerced.
        int_lists = {"by_second", "by_minute", "by_hour", "by_month_day",
                     "by_year_day", "by_week_no", "by_month", "by_set_pos"}
        fields = RecurrenceRule.part_names()
        r_data = {"unknown_parts": []}
        for rp in value.split(";"):
            if "=" not in rp:
                continue
            k, v = rp.split("=", 1)
            field = fields.get(k.upper())
            if field is None:
                r_data["unknown_parts"].append(rp)
            elif field == "frequency":
                r_data["frequency"] = v
            elif field == "until":
                r_data["until"] = DateTimeValue.parse(v)
            elif field in ("count", "interval"):
                try:
                    r_data[field] = int(v)
                except ValueError:
                    r_data["unknown_parts"].append(rp)
            elif field == "by_day":
                r_data[field] = v.split(",")
            elif field == "week_start":
                r_data[field] = v
            elif field in int_lists:
                try:
                    r_data[field] = [int(x) for x in v.split(",")]
                except ValueError:
                    r_data["unknown_parts"].append(rp)
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
    else:
        # Anything this parser does not model is preserved verbatim. Without
        # this branch an edit-and-write cycle silently strips every property
        # the model happens not to know -- CREATED, GEO, RELATED-TO and so on.
        data["unknown_properties"].append(line if line is not None else f"{key}:{value}")
    return data

# Components this parser models. Anything else (VTIMEZONE and its nested
# STANDARD/DAYLIGHT, VFREEBUSY, VAVAILABILITY, X- components) is captured
# verbatim rather than rejected -- an unrecognised component is a component we
# must hand back untouched, not a parse failure.
_KNOWN_COMPONENTS = {
    "VCALENDAR": ("ROOT",),
    "VCARD": ("ROOT",),
    "VEVENT": ("VCALENDAR",),
    "VTODO": ("VCALENDAR",),
    "VJOURNAL": ("VCALENDAR",),
    "VALARM": ("VEVENT", "VTODO", "VJOURNAL"),
}

_ITEM_COMPONENTS = ("VEVENT", "VTODO", "VJOURNAL")

def webdav_data(contents:str)->dict:
    from aloedav.model.m01_base import VCalendar, Alarm, Attendee, RecurrenceRule, Attachment

    lines = ModelUtil.unfold_lines(contents)
    context = [_init_data_dict({}, "ROOT")]

    context[0]["raw_contents"] = contents

    # Set while collecting an unmodelled component; its lines are buffered
    # verbatim (BEGIN and END included) and nesting is tracked by depth so an
    # inner BEGIN cannot terminate the outer block early.
    capture = None

    for line in lines:
        if ":" not in line: continue
        key, params, value = _decompose_line(line)

        if capture is not None:
            capture["lines"].append(line)
            if key == "BEGIN":
                capture["depth"] += 1
            elif key == "END":
                capture["depth"] -= 1
                if capture["depth"] == 0:
                    context[-1]["unknown_components"].append("\r\n".join(capture["lines"]))
                    capture = None
            continue

        current_context = context[-1]

        if key == "BEGIN":
            component = value.upper()
            allowed = _KNOWN_COMPONENTS.get(component)
            if allowed is None:
                capture = {"name": component, "depth": 1, "lines": [line]}
                continue
            if current_context["context"] not in allowed:
                raise ParseError(
                    f"BEGIN:{component} is not valid inside {current_context['context']} "
                    f"(expected one of {', '.join(allowed)})")
            context.append(_init_data_dict({}, component))
            continue

        elif key == "END":
            component = value.upper()
            if current_context["context"] != component:
                raise ParseError(
                    f"END:{component} does not match the open component "
                    f"{current_context['context']}")
            if len(context) < 2:
                raise ParseError(f"END:{component} with no enclosing component")
            parent_context = context[-2]
            if component in ("VCALENDAR", "VCARD"):
                parent_context["content"] = context.pop()
            elif component in _ITEM_COMPONENTS:
                parent_context["items"].append(context.pop())
            elif component == "VALARM":
                parent_context["alarms"].append(context.pop())
            context[-1] = parent_context

        elif current_context["context"] == "VALARM":
            context[-1] = _context_alarm(current_context, key, params, value, line)

        else:
            context[-1] = _context_item(current_context, key, params, value, line)

    if capture is not None:
        raise ParseError(f"BEGIN:{capture['name']} was never closed")
    if len(context) != 1:
        raise ParseError(f"unclosed component: {context[-1]['context']}")

    return context[0]

_ITEM_MODELS = {"VEVENT": VEVENT, "VTODO": VTODO, "VJOURNAL": VJOURNAL}

def to_resource(data, etag:str=None):
    """
    Parses one WebDAV resource into the unit the protocol actually moves.

    Unlike to_model, this keeps a VCALENDAR's components together, so a
    recurring master and its RECURRENCE-ID overrides survive as one resource
    with one filename instead of colliding and overwriting each other.
    """
    from aloedav.model.m01_resource import VCalendarResource, VCardResource

    data_dict = data if isinstance(data, dict) else webdav_data(data)
    content = data_dict["content"]
    raw = data_dict.get("raw_contents")

    if content["context"] == "VCARD":
        card = VCARD(**content)
        card.raw_contents = raw
        if etag:
            card.etag = etag
        return VCardResource(card=card, etag=etag, raw_contents=raw)

    elif content["context"] == "VCALENDAR":
        components = []
        for item in content["items"]:
            model = _ITEM_MODELS.get(item["context"])
            if model is None:
                raise ParseError(f"Unknown element type: {item['context']}")
            component = model(**item)
            component.raw_contents = raw
            if etag:
                component.etag = etag
            components.append(component)

        return VCalendarResource(
            version=content.get("version", "2.0"),
            prod_id=content.get("prod_id") or "-//aloecraft.org//AloeDAV 1.0//EN",
            components=components,
            calendar_properties=content.get("unknown_properties", []),
            calendar_components=content.get("unknown_components", []),
            etag=etag,
            raw_contents=raw)

    raise ParseError(f"Unknown element type: {content['context']}")

def to_model(data, etag:str=None)->list[VCARD|VTODO|VJOURNAL|VEVENT]:
    data_dict = data if isinstance(data, dict) else webdav_data(data)
    content = data_dict["content"]
    raw = data_dict.get("raw_contents")

    if content["context"] == "VCARD":
        vcard = VCARD(**content)
        vcard.raw_contents = raw
        if etag:
            vcard.etag = etag
        return [vcard]

    elif content["context"] == "VCALENDAR":
        # VCALENDAR-level content the model does not understand -- CALSCALE,
        # METHOD, and above all VTIMEZONE. It belongs to the enclosing calendar
        # rather than to any one component, so each item carries a copy and
        # re-emits it when serialized standalone.
        calendar_properties = content.get("unknown_properties", [])
        calendar_components = content.get("unknown_components", [])

        result = []
        for item in content["items"]:
            model = _ITEM_MODELS.get(item["context"])
            if model is None:
                raise ParseError(f"Unknown element type: {item['context']}")
            new_item = model(**item)
            new_item.raw_contents = raw
            new_item.calendar_properties = list(calendar_properties)
            new_item.calendar_components = list(calendar_components)
            if etag:
                new_item.etag = etag
            result.append(new_item)
        return result

    else:
        raise ParseError(f"Unknown element type: {content['context']}")