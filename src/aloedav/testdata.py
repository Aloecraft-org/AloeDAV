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