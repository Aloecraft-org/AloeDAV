from os import path
import xmltodict
import requests
from datetime import datetime
from typing import Tuple, Union
from aloedav.model.calendar import CalendarComponents
from aloedav.model.vcard    import VCard, Address, PhoneType, Phone, AddressType
from aloedav.model.vevent   import VEvent, Attendee, Alarm, RecurrenceRule, RecurrenceFrequency, Transparency, EventClass, EventStatus
from aloedav.model.vjournal import VJournal, Alarm, Attachment, RecurrenceRule, RecurrenceFrequency, JournalClass, JournalStatus
from aloedav.model.vtodo    import VTodo, Alarm, TodoStatus, TodoClass, RecurrenceFrequency, RecurrenceRule, Attendee

class AloeDAV:

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def _create(self, method, url, body=None):
        response = requests.request(method, url, data=body, auth=(self.username, self.password))

        if response.status_code in [201, 200]:
            print(f"Create Collection Success! '{url}' created and initialized.")
        elif response.status_code == 405:
            print(f"Create Collection '{url}' already exists.")
        else:
            print(f"Create Collection Failed: {response.status_code} - {response.text}")

    def _user_create_if_not_exists(self, username):
        user_url = path.join(self.host, username)
        self._create("MKCOL", user_url)

    def create_addressbook(self, display_name, description, addressbook_id):
        url = path.join(self.host, self.username, addressbook_id)
        body=f"""<?xml version="1.0" encoding="UTF-8" ?>
<D:mkcol xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:set>
    <D:prop>
      <D:displayname>{display_name}</D:displayname>
      <C:addressbook-description>{description}</C:addressbook-description>
      <D:resourcetype>
        <D:collection/>
        <C:addressbook/>
      </D:resourcetype>
    </D:prop>
  </D:set>
</D:mkcol>"""
        self._create("MKCOL", url,body)

    def create_calendar(self, display_name, description, calendar_id, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL):
        url = path.join(self.host, self.username, calendar_id)
        body=f"""<?xml version="1.0" encoding="UTF-8" ?>
<D:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:set>
    <D:prop>
      <D:displayname>{display_name}</D:displayname>
      <C:calendar-description>{description}</C:calendar-description>
      <C:supported-calendar-component-set>{
"        <C:comp name=\"VEVENT\"/>\n" if CalendarComponents.VEVENT in components else "" + \
"        <C:comp name=\"VTODO\"/>\n" if CalendarComponents.VTODO in components else "" + \
"        <C:comp name=\"VJOURNAL\"/>\n" if CalendarComponents.VJOURNAL in components else ""
      }
      </C:supported-calendar-component-set>
    </D:prop>
  </D:set>
</D:mkcalendar>
"""
        self._create("MKCALENDAR", url,body)

    def _extract_name_from_href(self, href):
        return href.rstrip('/').split('/')[-1]

    def delete_object(self, collection_id, filename, etag=None):
        url = path.join(self.host, self.username, collection_id, filename)
        headers = {}
        if etag:
            # WebDAV requires quoted ETags in If-Match, even if we strip them internally
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
        
        response = requests.delete(url, headers=headers, auth=(self.username, self.password))
        
        if response.status_code in [200, 204]:
            print(f"Deleted {filename}")
            return True
        elif response.status_code == 412:
            print(f"Delete failed: ETag mismatch for {filename}")
            return False
        else:
            print(f"Failed to delete: {response.status_code}")
            return False
    def list_collections(self):
        get_collections = lambda d: d.get('multistatus',{}).get('response',{})
        get_contenttype = lambda c: c.get('propstat',{}).get('prop',{}).get('getcontenttype')
        
        url = path.join(self.host, self.username)
        body = """<?xml version="1.0" encoding="utf-8" ?>
        <D:propfind xmlns:D="DAV:">
        <D:prop>
            <D:displayname/>
            <D:resourcetype/>
            <D:getcontenttype/>
        </D:prop>
        </D:propfind>"""

        response = requests.request("PROPFIND", url, data=body, headers={"Depth": "1"}, auth=(self.username,self.password))
        doc = xmltodict.parse(response.content)
        return [(c.get('href',''), get_contenttype(c)) for c in get_collections(doc) if type(c.get('propstat',{})) == dict]


    def list_calendar_objects(self, calendar_id, component_type="VEVENT", start: datetime = None, end: datetime = None):
        """
        Lists entries in a specific calendar, filtering by component type.
        component_type options: 'VEVENT', 'VTODO', 'VJOURNAL'
        """
        url = path.join(self.host, self.username, calendar_id)
        
        time_range_xml = ""
        if start and end:
            # CalDAV usually expects UTC YYYYMMDDTHHMMSSZ
            fmt = "%Y%m%dT%H%M%SZ"
            time_range_xml = f'<C:time-range start="{start.strftime(fmt)}" end="{end.strftime(fmt)}"/>'

        # Uses standard CalDAV filter to only return specific component types
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
    <C:filter>
        <C:comp-filter name="VCALENDAR">
            <C:comp-filter name="{component_type}">
                {time_range_xml}
            </C:comp-filter>
        </C:comp-filter>
    </C:filter>
</C:calendar-query>"""

        response = requests.request("REPORT", url, data=body, headers={"Depth": "1"}, auth=(self.username, self.password))
        
        # Parse XML and handle xmltodict's list/dict behavior for single vs multiple results
        doc = xmltodict.parse(response.content)
        responses = doc.get('multistatus', {}).get('response', [])
        if isinstance(responses, dict): responses = [responses]
        
        results = []
        for r in responses:
            propstat = r.get('propstat', {})
            # propstat is a list if there are mixed status codes; usually index 0 is the '200 OK' one
            if isinstance(propstat, list): propstat = propstat[0]
            
            props = propstat.get('prop', {})
            cal_data = props.get('C:calendar-data')
            # Fallback for ETag keys if namespace prefixes vary (D:getetag vs getetag)
            etag = props.get('D:getetag', props.get('getetag'))
            if etag and isinstance(etag, str):
                etag = etag.strip('"')
            if cal_data:
                # Returns the full href, etag, and the raw ICS data
                results.append({'href': r.get('href'), 'etag': etag, 'data': cal_data})
        return results

    def list_addressbook_entries(self, addressbook_id):
        """
        Lists all vCards in a specific addressbook.
        """
        url = path.join(self.host, self.username, addressbook_id)
        body = """<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
    <D:prop>
        <D:getetag/>
        <C:address-data/>
    </D:prop>
</C:addressbook-query>"""

        response = requests.request("REPORT", url, data=body, headers={"Depth": "1"}, auth=(self.username, self.password))
        
        doc = xmltodict.parse(response.content)
        responses = doc.get('multistatus', {}).get('response', [])
        if isinstance(responses, dict): responses = [responses]

        results = []
        for r in responses:
            propstat = r.get('propstat', {})
            if isinstance(propstat, list): propstat = propstat[0]
            
            props = propstat.get('prop', {})
            # Check for data with matching namespace or fallback
            card_data = props.get('C:address-data', props.get('CR:address-data'))
            etag = props.get('D:getetag', props.get('getetag'))
            if etag and isinstance(etag, str):
                etag = etag.strip('"')
            if card_data:
                results.append({'href': r.get('href'), 'etag': etag, 'data': card_data})
        return results

    def get_calendar_object(self, calendar_id, object_filename):
        """
        Retrieves a single calendar object (ics) by its filename.
        Example: object_filename = '1234-5678-90.ics'
        """
        url = path.join(self.host, self.username, calendar_id, object_filename)
        response = requests.get(url, auth=(self.username, self.password))
        
        if response.status_code == 200:
            etag = response.headers.get("ETag")
            if etag: etag = etag.strip('"')
            return response.text, etag
        else:
            print(f"Failed to retrieve calendar object: {response.status_code}")
            return None, None

    def get_addressbook_object(self, addressbook_id, object_filename):
        """
        Retrieves a single vCard (vcf) by its filename.
        Example: object_filename = 'contact-uid-123.vcf'
        """
        url = path.join(self.host, self.username, addressbook_id, object_filename)
        response = requests.get(url, auth=(self.username, self.password))
        
        if response.status_code == 200:
            etag = response.headers.get("ETag")
            if etag: etag = etag.strip('"')
            return response.text, etag
        else:
            print(f"Failed to retrieve contact: {response.status_code}")
            return None, None

    def get_vcard(self, addressbook_id: str, filename: str) -> Tuple[Union[VCard, None], Union[str, None]]:
        """
        High-level getter. Retrieves and deserializes a VCard.
        Returns (VCard_Object, ETag).
        """
        content, etag = self.get_addressbook_object(addressbook_id, filename)
        if not content:
            return None, None
        return VCard.from_vcard_string(content), etag

    def get_calendar_model(self, calendar_id: str, filename: str) -> Tuple[Union[VEvent, VTodo, VJournal, None], Union[str, None]]:
        """
        High-level getter. Retrieves and deserializes a VEvent, VTodo, or VJournal.
        Returns (Model_Object, ETag).
        """
        content, etag = self.get_calendar_object(calendar_id, filename)
        if not content:
            return None, None
        
        if "BEGIN:VEVENT" in content:
            return VEvent.from_vcalendar_string(content), etag
        elif "BEGIN:VTODO" in content:
            return VTodo.from_vcalendar_string(content), etag
        elif "BEGIN:VJOURNAL" in content:
            return VJournal.from_vcalendar_string(content), etag
        else:
            print(f"Warning: Unknown component type in {filename}")
            return None, etag
        
    def create_vcard(self, addressbook_id, vcard_obj: VCard):
        """
        Creates a new vCard in the specified addressbook using the Pydantic model.
        Returns the filename created.
        """
        # serialize to string
        vcard_data = vcard_obj.to_vcard_string()
        
        # If the Pydantic object doesn't have a UID yet, the serializer generated one. 
        # We use that UID for the filename typically.
        filename = f"{vcard_obj.uid}.vcf"
        
        url = path.join(self.host, self.username, addressbook_id, filename)
        
        # CardDAV uses PUT to create new resources
        headers = {"Content-Type": "text/vcard; charset=utf-8"}
        response = requests.put(url, data=vcard_data.encode('utf-8'), headers=headers, auth=(self.username, self.password))

        if response.status_code in [201, 204]:
            print(f"vCard created: {filename}")
            return filename
        else:
            print(f"Failed to create vCard: {response.status_code} - {response.text}")
            return None

    def update_vcard(self, addressbook_id, filename, vcard_obj: VCard, etag=None):
        """
        Updates an existing vCard.
        
        :param filename: The specific .vcf file resource (e.g., '12345.vcf')
        :param etag: Optional. If provided, ensures we don't overwrite changes made by others (If-Match).
        """
        url = path.join(self.host, self.username, addressbook_id, filename)
        
        # Ensure the UID in the object matches the filename (standard convention), 
        # though strictly speaking only the URL matters for the PUT.
        if not vcard_obj.uid:
            vcard_obj.uid = filename.replace('.vcf', '')

        vcard_data = vcard_obj.to_vcard_string()
        
        headers = {"Content-Type": "text/vcard; charset=utf-8"}
        if etag:
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag

        response = requests.put(url, data=vcard_data.encode('utf-8'), headers=headers, auth=(self.username, self.password))

        if response.status_code in [200, 204]:
            print(f"vCard updated: {filename}")
            return True
        elif response.status_code == 412:
            print("Update failed: ETag mismatch (resource has changed on server).")
            return False
        else:
            print(f"Failed to update vCard: {response.status_code} - {response.text}")
            return False


    def create_calendar_object(self, calendar_id, item_obj):
        """
        Creates a new calendar item (Event, Todo, or Journal).
        :param item_obj: An instance of VEvent, VTodo, or VJournal
        """
        # 1. Get the serialized string using the common interface
        ics_data = item_obj.to_vcalendar_string()
        
        # 2. Derive filename from UID. iCalendar files use .ics extension.
        filename = f"{item_obj.uid}.ics"
        
        url = path.join(self.host, self.username, calendar_id, filename)
        
        # 3. Send PUT request. Note the Content-Type is text/calendar.
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        response = requests.put(url, data=ics_data.encode('utf-8'), headers=headers, auth=(self.username, self.password))

        if response.status_code in [201, 204]:
            print(f"Calendar object created: {filename}")
            return filename
        else:
            print(f"Failed to create object: {response.status_code} - {response.text}")
            return None

    def update_calendar_object(self, calendar_id, filename, item_obj, etag=None):
        """
        Updates an existing calendar item.
        :param filename: The specific .ics file resource (e.g., 'event-123.ics')
        """
        url = path.join(self.host, self.username, calendar_id, filename)
        
        # Ensure UID matches filename (sanity check)
        if not item_obj.uid:
            item_obj.uid = filename.replace('.ics', '')

        ics_data = item_obj.to_vcalendar_string()
        
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag

        response = requests.put(url, data=ics_data.encode('utf-8'), headers=headers, auth=(self.username, self.password))
        
        if response.status_code in [200, 204]:
            print(f"Calendar object updated: {filename}")
            return True
        elif response.status_code == 412:
            print("Update failed: ETag mismatch (resource has changed on server).")
            return False
        else:
            print(f"Failed to update object: {response.status_code} - {response.text}")
            return False

if __name__ == "__main__" and False:
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  # If your server requires a password, add it here.
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    
    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook Lifecycle
    print("\n--- Testing Addressbook Lifecycle ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Delete Me",
        given_name="Delete",
        family_name="Me",
        emails=["delete.me@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # List & Verify ETag
    entries = aloedav.list_addressbook_entries(abook_id)
    target_entry = next((e for e in entries if fname in e['href']), None)
    
    if target_entry:
        print(f"Found in list. Href: {target_entry['href']}, ETag: {target_entry.get('etag')}")
        
        # Get specific object
        clean_name = aloedav._extract_name_from_href(target_entry['href'])
        content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        print(f"Fetched directly. ETag matches: {etag == target_entry.get('etag')}")

        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        contact.given_name = "UpdatedName"
        if aloedav.update_vcard(abook_id, clean_name, contact, etag=etag):
            print("Update successful.")
            # Refresh ETag after update for deletion
            content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")

        # Delete
        print(f"Deleting {clean_name} with ETag {etag}...")
        success = aloedav.delete_object(abook_id, clean_name, etag=etag)
        if success: 
            print("Deletion successful.")
        else:
            print("Deletion failed.")
    else:
        print("Error: Created contact not found in list.")


    # 3. Test Calendar Lifecycle
    print("\n--- Testing Calendar Lifecycle ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="Temporary Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname}")

    # List with Time Filter
    print("Listing events between 2026-01-09 and 2026-01-11...")
    events = aloedav.list_calendar_objects(
        cal_id, 
        component_type="VEVENT", 
        start=datetime(2026, 1, 9), 
        end=datetime(2026, 1, 11)
    )
    
    target_event = next((e for e in events if fname in e['href']), None)
    
    if target_event:
        print(f"Found event. ETag: {target_event.get('etag')}")
        
        # Get
        clean_name = aloedav._extract_name_from_href(target_event['href'])
        content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        
        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        event.summary = "Updated Summary"
        if aloedav.update_calendar_object(cal_id, clean_name, event, etag=etag):
            print("Update successful.")
            content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")
        
        # Delete
        print(f"Deleting {clean_name}...")
        aloedav.delete_object(cal_id, clean_name, etag=etag)
    else:
        print("Error: Created event not found in time-filtered list.")

    # outputs:
    # >--- Setting up Collections ---
    # >Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # >Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # ><error xmlns="DAV:"><resource-must-be-null /></error>
    # >Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # >------------------------------
    # >
    # >--- Testing Addressbook Lifecycle ---
    # >vCard created: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Created Contact: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Found in list. Href: /test/addressbook_test/e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf, ETag: b34cb7b5331f2cfa1601719d84d597ef4971fd68b9f9b9bfb30caaef481f7cd5
    # >Fetched directly. ETag matches: True
    # >Updating e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf (checking ETag logic)...
    # >vCard updated: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Update successful.
    # >Deleting e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf with ETag 8fb77052daf1b9173e775826097807733b9d0fdde37c610cabf62ea18cde00cd...
    # >Deleted e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Deletion successful.
    # >
    # >--- Testing Calendar Lifecycle ---
    # >Calendar object created: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Created Event: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Listing events between 2026-01-09 and 2026-01-11...
    # >Found event. ETag: a8181286c8949c13c76077c6d5d123997fbcd85002b0832c5921eea289906494
    # >Updating event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics (checking ETag logic)...
    # >Calendar object updated: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Update successful.
    # >Deleting event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics...
    # >Deleted event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics

if __name__ == "__main__":
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  # If your server requires a password, add it here.
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    
    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook Lifecycle
    print("\n--- Testing Addressbook Lifecycle ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Delete Me",
        given_name="Delete",
        family_name="Me",
        emails=["delete.me@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # List & Verify ETag
    entries = aloedav.list_addressbook_entries(abook_id)
    target_entry = next((e for e in entries if fname in e['href']), None)
    
    if target_entry:
        print(f"Found in list. Href: {target_entry['href']}, ETag: {target_entry.get('etag')}")
        
        # Get specific object
        clean_name = aloedav._extract_name_from_href(target_entry['href'])
        content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        print(f"Fetched directly. ETag matches: {etag == target_entry.get('etag')}")

        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        contact.given_name = "UpdatedName"
        if aloedav.update_vcard(abook_id, clean_name, contact, etag=etag):
            print("Update successful.")
            # Refresh ETag after update for deletion
            content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")

        # Delete
        print(f"Deleting {clean_name} with ETag {etag}...")
        success = aloedav.delete_object(abook_id, clean_name, etag=etag)
        if success: 
            print("Deletion successful.")
        else:
            print("Deletion failed.")
    else:
        print("Error: Created contact not found in list.")


    # 3. Test Calendar Lifecycle
    print("\n--- Testing Calendar Lifecycle ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="Temporary Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname}")

    # List with Time Filter
    print("Listing events between 2026-01-09 and 2026-01-11...")
    events = aloedav.list_calendar_objects(
        cal_id, 
        component_type="VEVENT", 
        start=datetime(2026, 1, 9), 
        end=datetime(2026, 1, 11)
    )
    
    target_event = next((e for e in events if fname in e['href']), None)
    
    if target_event:
        print(f"Found event. ETag: {target_event.get('etag')}")
        
        # Get
        clean_name = aloedav._extract_name_from_href(target_event['href'])
        content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        
        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        event.summary = "Updated Summary"
        if aloedav.update_calendar_object(cal_id, clean_name, event, etag=etag):
            print("Update successful.")
            content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")
        
        # Delete
        print(f"Deleting {clean_name}...")
        aloedav.delete_object(cal_id, clean_name, etag=etag)
    else:
        print("Error: Created event not found in time-filtered list.")

if __name__ == "__main__":
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook (Object Retrieval)
    print("\n--- Testing Addressbook High-Level Retrieval ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Deserialization Test",
        given_name="Deserialization",
        family_name="Test",
        emails=["test@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # Retrieve using High-Level Getter
    retrieved_contact, etag = aloedav.get_vcard(abook_id, fname)
    
    if retrieved_contact:
        print(f"Retrieved Object Type: {type(retrieved_contact).__name__}")
        print(f"Retrieved FN: {retrieved_contact.full_name}")
        print(f"ETag: {etag}")
        
        if retrieved_contact.full_name == "Deserialization Test":
            print("[PASS] VCard deserialized successfully.")
        else:
            print("[FAIL] VCard data mismatch.")
            
        # Clean up
        aloedav.delete_object(abook_id, fname, etag=etag)
    else:
        print("[FAIL] Could not retrieve VCard.")


    # 3. Test Calendar (Object Retrieval)
    print("\n--- Testing Calendar High-Level Retrieval ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="High Level Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname_evt = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname_evt}")

    # Create Todo
    todo_uid = f"todo-{uuid.uuid4()}"
    todo = VTodo(
        uid=todo_uid,
        summary="High Level Todo",
        dtstart=datetime(2026, 1, 12, 9, 0, 0),
        status=TodoStatus.NEEDS_ACTION
    )
    fname_todo = aloedav.create_calendar_object(cal_id, todo)
    print(f"Created Todo: {fname_todo}")

    # Retrieve Event
    retrieved_evt, etag_evt = aloedav.get_calendar_model(cal_id, fname_evt)
    if isinstance(retrieved_evt, VEvent):
        print(f"[PASS] Retrieved object is VEvent ({retrieved_evt.summary}).")
        aloedav.delete_object(cal_id, fname_evt, etag=etag_evt)
    else:
        print(f"[FAIL] Expected VEvent, got {type(retrieved_evt)}")

    # Retrieve Todo
    retrieved_todo, etag_todo = aloedav.get_calendar_model(cal_id, fname_todo)
    if isinstance(retrieved_todo, VTodo):
        print(f"[PASS] Retrieved object is VTodo ({retrieved_todo.summary}).")
        aloedav.delete_object(cal_id, fname_todo, etag=etag_todo)
    else:
        print(f"[FAIL] Expected VTodo, got {type(retrieved_todo)}")

    # outputs:
    
    # > --- Setting up Collections ---
    # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # > <error xmlns="DAV:"><resource-must-be-null /></error>
    # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # > ------------------------------
    # > 
    # > --- Testing Addressbook Lifecycle ---
    # > vCard created: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Created Contact: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Found in list. Href: /test/addressbook_test/7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf, ETag: 43ab5175234c1ab16e637fe1ebd30785f5e232e50fc7231e2424152cc7cf71af
    # > Fetched directly. ETag matches: True
    # > Updating 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf (checking ETag logic)...
    # > vCard updated: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Update successful.
    # > Deleting 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf with ETag bb6a4d4f5dfd1ee4d5b2aa2cdc62e21ec2c1fa890634ea5a1ab07af405c9efba...
    # > Deleted 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Deletion successful.
    # > 
    # > --- Testing Calendar Lifecycle ---
    # > Calendar object created: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Created Event: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Listing events between 2026-01-09 and 2026-01-11...
    # > Found event. ETag: 3dac627d1fdcd9544684a11367e287d98aebbe79207cb13e49dae899da488025
    # > Updating event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics (checking ETag logic)...
    # > Calendar object updated: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Update successful.
    # > Deleting event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics...
    # > Deleted event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > --- Setting up Collections ---
    # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # > <error xmlns="DAV:"><resource-must-be-null /></error>
    # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # > ------------------------------
    # > 
    # > --- Testing Addressbook High-Level Retrieval ---
    # > vCard created: 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > Created Contact: 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > Retrieved Object Type: VCard
    # > Retrieved FN: Deserialization Test
    # > ETag: 46457b4dea7f73b2deb66c7288b286870154acb04a0b56e9be5b9ed6e3ecee7a
    # > [PASS] VCard deserialized successfully.
    # > Deleted 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > 
    # > --- Testing Calendar High-Level Retrieval ---
    # > Calendar object created: event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > Created Event: event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > Calendar object created: todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics
    # > Created Todo: todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics
    # > [PASS] Retrieved object is VEvent (High Level Event).
    # > Deleted event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > [PASS] Retrieved object is VTodo (High Level Todo).
    # > Deleted todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics
