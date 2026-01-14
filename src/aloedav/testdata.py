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