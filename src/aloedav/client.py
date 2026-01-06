from os import path
import xmltodict
import requests
from datetime import datetime
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


    def list_calendar_objects(self, calendar_id, component_type="VEVENT"):
        """
        Lists entries in a specific calendar, filtering by component type.
        component_type options: 'VEVENT', 'VTODO', 'VJOURNAL'
        """
        url = path.join(self.host, self.username, calendar_id)
        
        # Uses standard CalDAV filter to only return specific component types
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
    <C:filter>
        <C:comp-filter name="VCALENDAR">
            <C:comp-filter name="{component_type}"/>
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
            
            cal_data = propstat.get('prop', {}).get('C:calendar-data')
            if cal_data:
                # Returns the full href and the raw ICS data
                results.append({'href': r.get('href'), 'data': cal_data})
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
            
            card_data = propstat.get('prop', {}).get('CR:address-data')
            if card_data:
                results.append({'href': r.get('href'), 'data': card_data})
        return results

    def get_calendar_object(self, calendar_id, object_filename):
        """
        Retrieves a single calendar object (ics) by its filename.
        Example: object_filename = '1234-5678-90.ics'
        """
        url = path.join(self.host, self.username, calendar_id, object_filename)
        response = requests.get(url, auth=(self.username, self.password))
        
        if response.status_code == 200:
            return response.text
        else:
            print(f"Failed to retrieve calendar object: {response.status_code}")
            return None

    def get_addressbook_object(self, addressbook_id, object_filename):
        """
        Retrieves a single vCard (vcf) by its filename.
        Example: object_filename = 'contact-uid-123.vcf'
        """
        url = path.join(self.host, self.username, addressbook_id, object_filename)
        response = requests.get(url, auth=(self.username, self.password))
        
        if response.status_code == 200:
            return response.text
        else:
            print(f"Failed to retrieve contact: {response.status_code}")
            return None
        

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
            headers["If-Match"] = etag

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
            headers["If-Match"] = etag

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

if __name__ == "main":

    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    NEW_USERNAME = "test"
    aloedav = AloeDAV(RADICALE_HOST, NEW_USERNAME, "")

    aloedav.create_addressbook("display_name", "description", "addressbook_id")
    aloedav.create_calendar("display_name", "description", "calendar_id", components=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL)
    print(aloedav.list_collections())

    # Create
    new_contact = VCard(
        fn="Jane Doe",
        given_name="Jane",
        categories=['someone', 'human'],
        family_name="Doe",
        emails=["jane@example.com"]
    )

    filename = aloedav.create_vcard("contacts", new_contact)

    event = VEvent(
        uid="event-123-456@example.com",
        summary="Team Standup Meeting",
        dtstart=datetime(2026, 1, 6, 10, 0, 0),
        dtend=datetime(2026, 1, 6, 10, 30, 0),
        location="Conference Room A",
        description="Daily team standup to sync on progress",
        organizer_name="Alice Johnson",
        organizer_email="alice@example.com",
        status=EventStatus.CONFIRMED,
        transparency=Transparency.OPAQUE,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.DAILY,
            interval=1,
            until=datetime(2026, 3, 31),
        ),
        attendees=[
            Attendee(
                email="bob@example.com",
                name="Bob Smith",
                participation_status="ACCEPTED",
            ),
            Attendee(
                email="charlie@example.com",
                name="Charlie Brown",
                participation_status="TENTATIVE",
            ),
        ],
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=15, description="Reminder"),
        ],
        categories=["WORK", "MEETING"],
    )


    todo = VTodo(
        uid="todo-789-012@example.com",
        summary="Prepare quarterly report",
        dtstart=datetime(2026, 1, 6, 9, 0, 0),
        due=datetime(2026, 1, 15, 17, 0, 0),
        description="Compile Q4 metrics and analysis for stakeholder presentation",
        status=TodoStatus.IN_PROCESS,
        priority=2,
        percent_complete=45,
        organizer_name="Alice Johnson",
        organizer_email="alice@example.com",
        attendees=[
            Attendee(
                email="david@example.com",
                name="David Lee",
                role="REQ-PARTICIPANT",
                participation_status="ACCEPTED",
            ),
        ],
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=1440, description="Due tomorrow"),
            Alarm(action="DISPLAY", trigger_minutes=60, description="Due in 1 hour"),
        ],
        categories=["WORK", "REPORTING"],
        location="Office",
    )
    
    recurring_todo = VTodo(
        uid="todo-recurring@example.com",
        summary="Weekly code review",
        dtstart=datetime(2026, 1, 6, 14, 0, 0),
        due=datetime(2026, 1, 9, 17, 0, 0),
        status=TodoStatus.COMPLETED,
        completed=datetime(2026, 1, 9, 16, 30, 0),
        percent_complete=100,
        priority=3,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.WEEKLY,
            interval=1,
        ),
        categories=["WORK", "DEVELOPMENT"],
    )
    

    vcard = VCard(
        fn="John Doe",
        given_name="John",
        family_name="Doe",
        categories=['someone', 'human'],
        emails=["john.doe@example.com"],
        phones=[
            Phone(number="+1-555-123-4567", type=PhoneType.CELL, is_preferred=True),
            Phone(number="+1-555-987-6543", type=PhoneType.WORK),
        ],
        addresses=[
            Address(
                street="123 Main St",
                city="Springfield",
                state="IL",
                postal_code="62701",
                country="USA",
                type=AddressType.HOME,
            )
        ],
        organization="Acme Corp",
        job_title="Software Engineer",
        url="https://johndoe.com",
        notes="Primary contact for project X",
    )

    journal_entry = VJournal(
        uid="journal-001@example.com",
        dtstart=datetime(2026, 1, 5, 18, 30, 0),
        summary="Reflection on Q1 Planning",
        description="Today was productive. We finalized the Q1 roadmap and got buy-in from stakeholders. "
                    "The team showed great enthusiasm for the new initiatives. Need to follow up on resource allocation by end of week.",
        status=JournalStatus.FINAL,
        classification=JournalClass.PRIVATE,
        organizer_name="Vera",
        organizer_email="vera@example.com",
        categories=["WORK", "PLANNING"],
        tags=["productivity", "teamwork", "quarterly-planning"],
    )

    daily_journal = VJournal(
        uid="daily-journal@example.com",
        dtstart=datetime(2026, 1, 6, 22, 0, 0),
        summary="Daily Reflection",
        description="A space for daily thoughts and reflections.",
        status=JournalStatus.DRAFT,
        classification=JournalClass.PRIVATE,
        recurrence_rule=RecurrenceRule(
            frequency=RecurrenceFrequency.DAILY,
            interval=1,
        ),
        alarms=[
            Alarm(action="DISPLAY", trigger_minutes=120, description="Evening reflection reminder"),
        ],
        categories=["PERSONAL"],
        tags=["daily", "reflection"],
    )
    
    # Update (Modify the object and send it back)
    new_contact.organization = "New Corp"
    aloedav.update_vcard("contacts", filename, new_contact)
    print(aloedav.list_addressbook_entries("addressbook_id"))
    print(aloedav.list_calendar_objects("calendar_id", component_type="VEVENT"))

    aloedav.get_calendar_object(self, calendar_id, object_filename)
    aloedav.get_addressbook_object(self, addressbook_id, object_filename)