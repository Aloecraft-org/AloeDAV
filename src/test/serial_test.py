import unittest
import json
from datetime import datetime, date
from aloedav.model.serial_util import webdav_data, to_model
from aloedav.testdata import TEST_VCARD_FOLDED, TEST_VCARD_SIMPLE, TEST_VEVENT_FOLDED, TEST_VEVENT_SIMPLE
from aloedav.testdata import TEST_VEVENT_COMPLEX, TEST_VTODO_WITH_ALARM, TEST_VCALENDAR_MIXED, TEST_VCARD_RICH
from aloedav.testdata import TEST_VCARD_SIMPLE_DICT, TEST_VCARD_FOLDED_DICT, TEST_VEVENT_SIMPLE_DICT, TEST_VEVENT_FOLDED_DICT
from aloedav.testdata import TEST_VEVENT_COMPLEX_DICT, TEST_VTODO_WITH_ALARM_DICT, TEST_VCALENDAR_MIXED_DICT, TEST_VCARD_RICH_DICT

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)): # Need to import date as well for date objects
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

maxDiff = None  # Important: This lets you see the full diff if a test fails

class TestFuncs(unittest.TestCase):
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

    def test_TEST_VCARD_SIMPLE(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VCARD_SIMPLE)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)

        self.assertEqual(data_dict, TEST_VCARD_SIMPLE_DICT)
        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        card = items[0]
        self.assertEqual(card.fn, "Forrest Gump")
        self.assertEqual(card.organization, "Bubba Gump Shrimp Co.")
        # Verify list contents
        self.assertEqual(card.emails[0], "forrestgump@example.com")
        self.assertEqual(card.phones[0].number, "(111) 555-1212")

    def test_TEST_VCARD_FOLDED(self):

        # 1. Parse the data
        raw_data = webdav_data(TEST_VCARD_FOLDED)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, TEST_VCARD_FOLDED_DICT)

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        # Verify model attributes directly
        card = items[0]
        self.assertEqual(card.fn, "Folded Line Tester")
        # Check that the folded lines were reconstructed correctly
        self.assertEqual(card.addresses[0].street, "100 Waters Edge")
        self.assertEqual(card.addresses[0].country, "United States of America")
        self.assertTrue("unfolding logic" in card.notes)

    def test_TEST_VEVENT_SIMPLE(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_SIMPLE)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, TEST_VEVENT_SIMPLE_DICT)

        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        event = items[0]
        self.assertEqual(event.uid, "19970610T172345Z-AF23B2@example.com")
        self.assertEqual(event.summary, "Bastille Day Party")
        # Verify date parsing result
        self.assertEqual(event.dtstart.year, 1997)
        self.assertEqual(event.dtstart.month, 7)

    def test_TEST_VEVENT_FOLDED(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_FOLDED)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, TEST_VEVENT_FOLDED_DICT)
        items = to_model(data_dict)
        self.assertEqual(len(items),1)

        event = items[0]
        self.assertEqual(event.summary, "Project Planning Meeting")
        # Ensure description folding was handled (no extra spaces or newlines at fold points)
        self.assertTrue("legacy backend systems" in event.description)
        # Ensure location folding was handled
        self.assertEqual(event.location, "Conference Room B with the really long name that forces a line break in the middle of the word.")



    def test_TEST_VEVENT_COMPLEX(self):
        # 1. Parse the data
        raw_data = webdav_data(TEST_VEVENT_COMPLEX)
        # 2. Normalize it (convert dates/enums to strings)
        data_dict = self.normalize(raw_data)
        
        self.assertEqual(data_dict, TEST_VEVENT_COMPLEX_DICT)

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
        
        self.assertEqual(data_dict, TEST_VTODO_WITH_ALARM_DICT)

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
        
        self.assertEqual(data_dict, TEST_VCALENDAR_MIXED_DICT)

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
        
        self.assertEqual(data_dict, TEST_VCARD_RICH_DICT)

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
        self.assertEqual(card.addresses[1].type.value, "home") 