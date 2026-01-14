import unittest
import json
from datetime import datetime, date
from aloedav.model.serial_util import webdav_data, to_model
from aloedav.testdata import TEST_VCARD_FOLDED, TEST_VCARD_SIMPLE, TEST_VEVENT_FOLDED, TEST_VEVENT_SIMPLE
from aloedav.testdata import TEST_VEVENT_COMPLEX, TEST_VTODO_WITH_ALARM, TEST_VCALENDAR_MIXED, TEST_VCARD_RICH

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)): # Need to import date as well for date objects
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

class TestFuncs(unittest.TestCase):

    maxDiff = None  # Important: This lets you see the full diff if a test fails

    def normalize(self, data):
        """
        Converts complex objects (datetimes, Enums) into strings 
        so they match the expected dictionary structure.
        """
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if hasattr(obj, "value"):  # Handle Enums (PhoneType, AddressType)
                return obj.value
            raise TypeError(f"Type {type(obj)} not serializable")
            
        # Dump to string and load back to dict to get pure primitives
        return json.loads(json.dumps(data, default=json_serial))

    def test_1(self):
        print(f"===============================\nTEST_VCARD_FOLDED    \n==============================={\
            json.dumps(webdav_data(TEST_VCARD_FOLDED), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VCARD_SIMPLE    \n==============================={\
            json.dumps(webdav_data(TEST_VCARD_SIMPLE), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VEVENT_FOLDED   \n==============================={\
            json.dumps(webdav_data(TEST_VEVENT_FOLDED), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VEVENT_SIMPLE   \n==============================={\
            json.dumps(webdav_data(TEST_VEVENT_SIMPLE), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VEVENT_COMPLEX  \n==============================={\
            json.dumps(webdav_data(TEST_VEVENT_COMPLEX), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VTODO_WITH_ALARM\n==============================={\
            json.dumps(webdav_data(TEST_VTODO_WITH_ALARM), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VCALENDAR_MIXED \n==============================={\
            json.dumps(webdav_data(TEST_VCALENDAR_MIXED), indent=4, default=json_serial)\
        }")
        print(f"===============================\nTEST_VCARD_RICH      \n==============================={\
            json.dumps(webdav_data(TEST_VCARD_RICH), indent=4, default=json_serial)\
        }")

    def test_TEST_VCARD_FOLDED(self):

        # 1. Parse the data
        raw_data = webdav_data(TEST_VCARD_FOLDED)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        # Verify model attributes directly
        card = items[0]
        self.assertEqual(card.fn, "Folded Line Tester")
        # Check that the folded lines were reconstructed correctly
        self.assertEqual(card.addresses[0].street, "100 Waters Edge")
        self.assertEqual(card.addresses[0].country, "United States of America")
        self.assertTrue("unfolding logic" in card.notes)

    def test_TEST_VCARD_SIMPLE(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VCARD_SIMPLE)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)

        self.assertEqual(data_dict, {
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
        })
        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        card = items[0]
        self.assertEqual(card.fn, "Forrest Gump")
        self.assertEqual(card.organization, "Bubba Gump Shrimp Co.")
        # Verify list contents
        self.assertEqual(card.emails[0], "forrestgump@example.com")
        self.assertEqual(card.phones[0].number, "(111) 555-1212")

    def test_TEST_VEVENT_FOLDED(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_FOLDED)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })
        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        event = items[0]
        self.assertEqual(event.summary, "Project Planning Meeting")
        # Ensure description folding was handled (no extra spaces or newlines at fold points)
        self.assertTrue("legacy backend systems" in event.description)
        # Ensure location folding was handled
        self.assertEqual(event.location, "Conference Room B with the really long name that forces a line break in the middle of the word.")

    def test_TEST_VEVENT_SIMPLE(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_SIMPLE)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        event = items[0]
        self.assertEqual(event.uid, "19970610T172345Z-AF23B2@example.com")
        self.assertEqual(event.summary, "Bastille Day Party")
        # Verify date parsing result
        self.assertEqual(event.dtstart.year, 1997)
        self.assertEqual(event.dtstart.month, 7)

    def test_TEST_VEVENT_COMPLEX(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_COMPLEX)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        event = items[0]
        self.assertEqual(event.summary, "Weekly Project Sync")
        
        # Check Attendees
        self.assertEqual(len(event.attendees), 2)
        self.assertEqual(event.attendees[0].name, "Project Lead")
        self.assertEqual(event.attendees[1].role, "OPT-PARTICIPANT")
        
        # Check Recurrence
        self.assertEqual(event.recurrence_rule.frequency, "WEEKLY")
        self.assertEqual(event.recurrence_rule.count, 10)
        
        # Check Attachments
        self.assertEqual(len(event.attachments), 1)
        self.assertEqual(event.attachments[0].filename, "agenda.pdf")

    def test_TEST_VTODO_WITH_ALARM(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VTODO_WITH_ALARM)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        todo = items[0]
        self.assertEqual(todo.summary, "Submit Quarterly Report")
        self.assertEqual(todo.priority, 1)
        
        # Check nested Alarm model
        self.assertEqual(len(todo.alarms), 1)
        alarm = todo.alarms[0]
        self.assertEqual(alarm.action, "DISPLAY")
        self.assertEqual(alarm.trigger_minutes, 15)

    def test_TEST_VCALENDAR_MIXED(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VCALENDAR_MIXED)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),2)

        # Verify we got two distinct objects in the correct order
        event = items[0]
        todo = items[1]
        
        # Check Event
        self.assertEqual(event.summary, "Lunch with Client")
        
        # Check Todo and relationship
        self.assertEqual(todo.summary, "Prepare Invoice for Lunch")
        self.assertEqual(todo.related_to, event.uid)

    def test_TEST_VCARD_RICH(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VCARD_RICH)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, {
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
        })

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        card = items[0]
        self.assertEqual(card.fn, "Rich Data User")
        
        # Check counts to ensure no data was dropped
        self.assertEqual(len(card.emails), 2)
        self.assertEqual(len(card.phones), 3)
        self.assertEqual(len(card.addresses), 2)
        
        # Check specific nested data
        self.assertEqual(card.emails[1], "rich.user@personal.example.com")
        self.assertEqual(card.addresses[0].city, "Tech City")
        self.assertEqual(card.addresses[1].type.value, "home") # Assuming AddressType enum value is 'home'