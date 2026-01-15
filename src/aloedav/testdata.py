# Simple vCard without complex folding
TEST_VCARD_SIMPLE = """BEGIN:VCARD
VERSION:3.0
FN:Forrest Gump
N:Gump;Forrest;;Mr.;
ORG:Bubba Gump Shrimp Co.
TITLE:Shrimp Man
TEL;TYPE=WORK,VOICE:(111) 555-1212
EMAIL;TYPE=PREF,INTERNET:forrestgump@example.com
END:VCARD"""

TEST_VCARD_SIMPLE_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCARD",
        "unknown_attributes": [],
        "extended_attributes": {},
        "fn": "Forrest Gump",
        "emails": [
            "forrestgump@example.com"
        ],
        "phones": [
            {
                "number": "(111) 555-1212",
                "type": "voice",
                "is_preferred": False
            }
        ],
        "addresses": [],
        "categories": [],
        "version": "3.0",
        "family_name": "Gump",
        "given_name": "Forrest",
        "organization": "Bubba Gump Shrimp Co.",
        "job_title": "Shrimp Man",
        'prod_id': None,
    },
    "raw_contents": "BEGIN:VCARD\nVERSION:3.0\nFN:Forrest Gump\nN:Gump;Forrest;;Mr.;\nORG:Bubba Gump Shrimp Co.\nTITLE:Shrimp Man\nTEL;TYPE=WORK,VOICE:(111) 555-1212\nEMAIL;TYPE=PREF,INTERNET:forrestgump@example.com\nEND:VCARD"
}

# vCard with line folding (lines starting with space)
# Note the split in the NOTE and ADR fields
TEST_VCARD_FOLDED = """BEGIN:VCARD
VERSION:3.0
FN:Folded Line Tester
N:Tester;Folded;;;
NOTE:This is a long note that is folded over multiple lines to test the unfo
 lding logic of the utility function. It should appear as a single continuous
  line after processing.
ADR;TYPE=WORK:;;100 Waters Edge;Baytown;LA;30314;United States of Amer
 ica
END:VCARD"""

TEST_VCARD_FOLDED_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCARD",
        "unknown_attributes": [],
        "extended_attributes": {},
        "fn": "Folded Line Tester",
        "emails": [],
        "phones": [],
        "addresses": [
            {
                "street": "100 Waters Edge",
                "city": "Baytown",
                "state": "LA",
                "postal_code": "30314",
                "country": "United States of America",
                "type": "work"
            }
        ],
        "categories": [],
        "version": "3.0",
        "family_name": "Tester",
        "given_name": "Folded",
        "notes": "This is a long note that is folded over multiple lines to test the unfolding logic of the utility function. It should appear as a single continuous line after processing.",
        'prod_id': None
    },
    "raw_contents": "BEGIN:VCARD\nVERSION:3.0\nFN:Folded Line Tester\nN:Tester;Folded;;;\nNOTE:This is a long note that is folded over multiple lines to test the unfo\n lding logic of the utility function. It should appear as a single continuous\n  line after processing.\nADR;TYPE=WORK:;;100 Waters Edge;Baytown;LA;30314;United States of Amer\n ica\nEND:VCARD"
}

# Simple Calendar Event
TEST_VEVENT_SIMPLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//hacksw/handcal//NONSGML v1.0//EN
BEGIN:VEVENT
UID:19970610T172345Z-AF23B2@example.com
DTSTAMP:19970610T172345Z
DTSTART:19970714T170000Z
DTEND:19970715T035959Z
SUMMARY:Bastille Day Party
END:VEVENT
END:VCALENDAR"""

TEST_VEVENT_SIMPLE_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCALENDAR",
        "unknown_attributes": [],
        "extended_attributes": {},
        "items": [
            {
                "context": "VEVENT",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [],
                "alarms": [],
                "categories": [],
                "attachments": [],
                "uid": "19970610T172345Z-AF23B2@example.com",
                "dtstamp": "1997-06-10T17:23:45",
                "dtstart": "1997-07-14T17:00:00",
                "dtend": "1997-07-15T03:59:59",
                "summary": "Bastille Day Party"
            }
        ],
        "version": "2.0",
        "prod_id": "-//hacksw/handcal//NONSGML v1.0//EN"
    },
    "raw_contents": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//hacksw/handcal//NONSGML v1.0//EN\nBEGIN:VEVENT\nUID:19970610T172345Z-AF23B2@example.com\nDTSTAMP:19970610T172345Z\nDTSTART:19970714T170000Z\nDTEND:19970715T035959Z\nSUMMARY:Bastille Day Party\nEND:VEVENT\nEND:VCALENDAR"
}

# Calendar Event with folding in DESCRIPTION and LOCATION
TEST_VEVENT_FOLDED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp//CalDAV Client//EN
BEGIN:VEVENT
UID:20260106T120000Z-123456@example.com
DTSTAMP:20260106T120000Z
DTSTART:20260106T130000Z
SUMMARY:Project Planning Meeting
DESCRIPTION:We will discuss the roadmap for the upcoming quarter, specificall
 y focusing on the integration of the new AI modules and the legacy backend s
 ystems. Please come prepared with your status reports.
LOCATION:Conference Room B with the really long name that forces a line break
  in the middle of the word.
END:VEVENT
END:VCALENDAR"""

TEST_VEVENT_FOLDED_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCALENDAR",
        "unknown_attributes": [],
        "extended_attributes": {},
        "items": [
            {
                "context": "VEVENT",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [],
                "alarms": [],
                "categories": [],
                "attachments": [],
                "uid": "20260106T120000Z-123456@example.com",
                "dtstamp": "2026-01-06T12:00:00",
                "dtstart": "2026-01-06T13:00:00",
                "summary": "Project Planning Meeting",
                "description": "We will discuss the roadmap for the upcoming quarter, specifically focusing on the integration of the new AI modules and the legacy backend systems. Please come prepared with your status reports.",
                "location": "Conference Room B with the really long name that forces a line break in the middle of the word."
            }
        ],
        "version": "2.0",
        "prod_id": "-//Example Corp//CalDAV Client//EN"
    },
    "raw_contents": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Example Corp//CalDAV Client//EN\nBEGIN:VEVENT\nUID:20260106T120000Z-123456@example.com\nDTSTAMP:20260106T120000Z\nDTSTART:20260106T130000Z\nSUMMARY:Project Planning Meeting\nDESCRIPTION:We will discuss the roadmap for the upcoming quarter, specificall\n y focusing on the integration of the new AI modules and the legacy backend s\n ystems. Please come prepared with your status reports.\nLOCATION:Conference Room B with the really long name that forces a line break\n  in the middle of the word.\nEND:VEVENT\nEND:VCALENDAR"
}


# Calendar with VEVENT containing Recursion (RRULE), Attendees, and Attachments
TEST_VEVENT_COMPLEX = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AloeDav//Test//EN
BEGIN:VEVENT
UID:recur-meeting-123@example.com
DTSTAMP:20260114T100000Z
DTSTART:20260201T090000Z
DURATION:PT1H
SUMMARY:Weekly Project Sync
DESCRIPTION:Weekly sync to discuss project blockers.
RRULE:FREQ=WEEKLY;COUNT=10;INTERVAL=1
ATTENDEE;CN=Project Lead;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED:mailto:lead@example.com
ATTENDEE;CN=Developer;ROLE=OPT-PARTICIPANT;PARTSTAT=NEEDS-ACTION:mailto:dev@example.com
ATTACH;FMTTYPE=application/pdf:http://example.com/docs/agenda.pdf
CATEGORIES:MEETING,PROJECT-A
END:VEVENT
END:VCALENDAR"""

TEST_VEVENT_COMPLEX_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCALENDAR",
        "unknown_attributes": [],
        "extended_attributes": {},
        "items": [
            {
                "context": "VEVENT",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [
                    {
                        "email": "lead@example.com",
                        "name": "Project Lead",
                        "role": "REQ-PARTICIPANT",
                        "participation_status": "ACCEPTED"
                    },
                    {
                        "email": "dev@example.com",
                        "name": "Developer",
                        "role": "OPT-PARTICIPANT",
                        "participation_status": "NEEDS-ACTION"
                    }
                ],
                "alarms": [],
                "categories": [
                    "MEETING",
                    "PROJECT-A"
                ],
                "attachments": [
                    {
                        "filename": "agenda.pdf",
                        "mime_type": "application/pdf",
                        "url": "http://example.com/docs/agenda.pdf"
                    }
                ],
                "uid": "recur-meeting-123@example.com",
                "dtstamp": "2026-01-14T10:00:00",
                "dtstart": "2026-02-01T09:00:00",
                "duration": "PT1H",
                "summary": "Weekly Project Sync",
                "description": "Weekly sync to discuss project blockers.",
                "recurrence_rule": {
                    "frequency": "WEEKLY",
                    "count": 10,
                    "interval": 1
                }
            }
        ],
        "version": "2.0",
        "prod_id": "-//AloeDav//Test//EN"
    },
    "raw_contents": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//AloeDav//Test//EN\nBEGIN:VEVENT\nUID:recur-meeting-123@example.com\nDTSTAMP:20260114T100000Z\nDTSTART:20260201T090000Z\nDURATION:PT1H\nSUMMARY:Weekly Project Sync\nDESCRIPTION:Weekly sync to discuss project blockers.\nRRULE:FREQ=WEEKLY;COUNT=10;INTERVAL=1\nATTENDEE;CN=Project Lead;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED:mailto:lead@example.com\nATTENDEE;CN=Developer;ROLE=OPT-PARTICIPANT;PARTSTAT=NEEDS-ACTION:mailto:dev@example.com\nATTACH;FMTTYPE=application/pdf:http://example.com/docs/agenda.pdf\nCATEGORIES:MEETING,PROJECT-A\nEND:VEVENT\nEND:VCALENDAR"
}

# Calendar with VTODO and embedded VALARM
TEST_VTODO_WITH_ALARM = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AloeDav//Test//EN
BEGIN:VTODO
UID:task-456@example.com
DTSTAMP:20260114T120000Z
DUE:20260120T170000Z
SUMMARY:Submit Quarterly Report
STATUS:NEEDS-ACTION
PRIORITY:1
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Reminder: Submit Report Now
TRIGGER:-PT15M
END:VALARM
END:VTODO
END:VCALENDAR"""

TEST_VTODO_WITH_ALARM_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCALENDAR",
        "unknown_attributes": [],
        "extended_attributes": {},
        "items": [
            {
                "context": "VTODO",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [],
                "alarms": [
                    {
                        "context": "VALARM",
                        "unknown_attributes": [],
                        "action": "DISPLAY",
                        "description": "Reminder: Submit Report Now",
                        "trigger_minutes": 15
                    }
                ],
                "categories": [],
                "attachments": [],
                "uid": "task-456@example.com",
                "dtstamp": "2026-01-14T12:00:00",
                "due": "2026-01-20T17:00:00",
                "summary": "Submit Quarterly Report",
                "status": "NEEDS-ACTION",
                "priority": 1
            }
        ],
        "version": "2.0",
        "prod_id": "-//AloeDav//Test//EN"
    },
    "raw_contents": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//AloeDav//Test//EN\nBEGIN:VTODO\nUID:task-456@example.com\nDTSTAMP:20260114T120000Z\nDUE:20260120T170000Z\nSUMMARY:Submit Quarterly Report\nSTATUS:NEEDS-ACTION\nPRIORITY:1\nBEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Reminder: Submit Report Now\nTRIGGER:-PT15M\nEND:VALARM\nEND:VTODO\nEND:VCALENDAR"
}

# Calendar with Multiple Mixed Items (VEVENT + VTODO)
TEST_VCALENDAR_MIXED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AloeDav//Test//EN
BEGIN:VEVENT
UID:event-001@example.com
DTSTART:20260301T120000Z
SUMMARY:Lunch with Client
END:VEVENT
BEGIN:VTODO
UID:task-001@example.com
SUMMARY:Prepare Invoice for Lunch
RELATED-TO:event-001@example.com
END:VTODO
END:VCALENDAR"""

TEST_VCALENDAR_MIXED_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCALENDAR",
        "unknown_attributes": [],
        "extended_attributes": {},
        "items": [
            {
                "context": "VEVENT",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [],
                "alarms": [],
                "categories": [],
                "attachments": [],
                "uid": "event-001@example.com",
                "dtstart": "2026-03-01T12:00:00",
                "summary": "Lunch with Client"
            },
            {
                "context": "VTODO",
                "unknown_attributes": [],
                "extended_attributes": {},
                "attendees": [],
                "alarms": [],
                "categories": [],
                "attachments": [],
                "uid": "task-001@example.com",
                "summary": "Prepare Invoice for Lunch",
                "related_to": "event-001@example.com"
            }
        ],
        "version": "2.0",
        "prod_id": "-//AloeDav//Test//EN"
    },
    "raw_contents": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//AloeDav//Test//EN\nBEGIN:VEVENT\nUID:event-001@example.com\nDTSTART:20260301T120000Z\nSUMMARY:Lunch with Client\nEND:VEVENT\nBEGIN:VTODO\nUID:task-001@example.com\nSUMMARY:Prepare Invoice for Lunch\nRELATED-TO:event-001@example.com\nEND:VTODO\nEND:VCALENDAR"
}

# Complex vCard with multiple Addresses and Phone Numbers
TEST_VCARD_RICH = """BEGIN:VCARD
VERSION:3.0
FN:Rich Data User
N:User;Rich;;;
ORG:Enterprise Corp
TITLE:Senior Tester
EMAIL;TYPE=INTERNET,PREF:rich.user@work.example.com
EMAIL;TYPE=INTERNET:rich.user@personal.example.com
TEL;TYPE=WORK,VOICE:(555) 123-4567
TEL;TYPE=HOME,VOICE:(555) 987-6543
TEL;TYPE=CELL:(555) 555-5555
ADR;TYPE=WORK:;;100 Enterprise Way;Tech City;CA;90210;USA
ADR;TYPE=HOME:;;42 Quiet Lane;Suburbia;CA;90211;USA
NOTE:This contact has multiple emails, phones, and addresses to test list appending.
END:VCARD"""


TEST_VCARD_RICH_DICT = {
    "context": "ROOT",
    "unknown_attributes": [],
    "content": {
        "context": "VCARD",
        "unknown_attributes": [],
        "extended_attributes": {},
        "fn": "Rich Data User",
        "emails": [
            "rich.user@work.example.com",
            "rich.user@personal.example.com"
        ],
        "phones": [
            {
                "number": "(555) 123-4567",
                "type": "voice",
                "is_preferred": False
            },
            {
                "number": "(555) 987-6543",
                "type": "voice",
                "is_preferred": False
            },
            {
                "number": "(555) 555-5555",
                "type": "cell",
                "is_preferred": False
            }
        ],
        "addresses": [
            {
                "street": "100 Enterprise Way",
                "city": "Tech City",
                "state": "CA",
                "postal_code": "90210",
                "country": "USA",
                "type": "work"
            },
            {
                "street": "42 Quiet Lane",
                "city": "Suburbia",
                "state": "CA",
                "postal_code": "90211",
                "country": "USA",
                "type": "home"
            }
        ],
        "categories": [],
        "version": "3.0",
        "family_name": "User",
        "given_name": "Rich",
        "organization": "Enterprise Corp",
        "job_title": "Senior Tester",
        "notes": "This contact has multiple emails, phones, and addresses to test list appending.",
        'prod_id': None,
    },
    "raw_contents": "BEGIN:VCARD\nVERSION:3.0\nFN:Rich Data User\nN:User;Rich;;;\nORG:Enterprise Corp\nTITLE:Senior Tester\nEMAIL;TYPE=INTERNET,PREF:rich.user@work.example.com\nEMAIL;TYPE=INTERNET:rich.user@personal.example.com\nTEL;TYPE=WORK,VOICE:(555) 123-4567\nTEL;TYPE=HOME,VOICE:(555) 987-6543\nTEL;TYPE=CELL:(555) 555-5555\nADR;TYPE=WORK:;;100 Enterprise Way;Tech City;CA;90210;USA\nADR;TYPE=HOME:;;42 Quiet Lane;Suburbia;CA;90211;USA\nNOTE:This contact has multiple emails, phones, and addresses to test list appending.\nEND:VCARD"
}