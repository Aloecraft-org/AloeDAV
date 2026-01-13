from logging import info, error

from os import path
import xmltodict
import requests
from datetime import datetime
from typing import Tuple, Union, List, Dict
from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.model.m00_constant import CalendarComponents, TodoStatus
from aloedav.model.vcard    import VCard
from aloedav.model.vevent   import VEvent
from aloedav.model.vjournal import VJournal
from aloedav.model.vtodo    import VTodo

# class AloeDAV:
#     def __init__(self, host, username, password):
#     def _create(self, method, url, body=None):
#     def _user_create_if_not_exists(self, username):
#     def create_addressbook(self, display_name, description, addressbook_id):
#     def create_calendar(self, display_name, description, calendar_id, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL):
#     def _extract_name_from_href(self, href):
#     def delete_object(self, collection_id, filename, etag=None):
#     def list_collections(self):
#     def list_calendar_objects(self, calendar_id, component_type="VEVENT", start: datetime = None, end: datetime = None):
#     def list_addressbook_entries(self, addressbook_id)-> dict
#     def get_calendar_object(self, calendar_id, object_filename)->tuple[str,str]:
#     def get_addressbook_object(self, addressbook_id, object_filename)->tuple[str,str]:
#     def get_vcard(self, addressbook_id: str, filename: str) -> Tuple[Union[VCard, None], Union[str, None]]:
#     def get_calendar_model(self, calendar_id: str, filename: str) -> Tuple[Union[VEvent, VTodo, VJournal, None], Union[str, None]]:
#     def get_sync_token(self, collection_id: str) -> Union[str, None]:
#     def sync_collection(self, collection_id: str, sync_token: str = "") -> Tuple[List[Dict], List[str], str]:
#     def create_vcard(self, addressbook_id, vcard_obj: VCard) -> str
#     def update_vcard(self, addressbook_id, filename, vcard_obj: VCard, etag=None) -> bool
#     def create_calendar_object(self, calendar_id, item_obj) -> str:
#     def update_calendar_object(self, calendar_id, filename, item_obj, etag=None) -> bool

class AloeDAV:

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def _with_auth(username, password, session):
        TAG="[AloeDAV._with_auth]"

    def _create(self, method, url, body=None) -> bool:
        TAG="[AloeDAV._create]"
        response = requests.request(method, url, data=body, auth=(self.username, self.password))

        if response.status_code in [201, 200]:
            # Success
            info(f"{TAG} Collection created: {url}")
            return True
        elif response.status_code == 405:
            # Collection already exists (MKCOL returns 405 Method Not Allowed on existing resource)
            info(f"{TAG} Collection already exists: {url}")
            return False
        elif response.status_code == 409 and "resource-must-be-null" in response.text:
            # Collection already exists (409 Conflict: resource-must-be-null)
            info(f"{TAG} Collection already exists: {url}")
            return False
        elif response.status_code == 401:
            error(f"{TAG} Authentication failed for: {url}")
            raise AuthenticationError(f"Authentication failed for {url} - {response.text}", response.status_code)
        else:
            error(f"{TAG} Create Collection failed for: {url} - {response.text}")
            raise WebDAVError(f"Create Collection Failed: {response.status_code}", response.status_code, response.text)

    def _user_create_if_not_exists(self, username):
        user_url = path.join(self.host, username)
        self._create("MKCOL", user_url)

    def create_addressbook(self, display_name, description, addressbook_id) -> bool:
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
        return self._create("MKCOL", url, body)

    def create_calendar(self, display_name, description, calendar_id, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL)  -> bool:
        url = path.join(self.host, self.username, calendar_id)
        body=f"""<?xml version="1.0" encoding="UTF-8" ?>
<D:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:set>
    <D:prop>
      <D:displayname>{display_name}</D:displayname>
      <C:calendar-description>{description}</C:calendar-description>
      <C:supported-calendar-component-set>{
("        <C:comp name=\"VEVENT\"/>\n" if CalendarComponents.VEVENT in components else "") + \
("        <C:comp name=\"VTODO\"/>\n" if CalendarComponents.VTODO in components else "") + \
("        <C:comp name=\"VJOURNAL\"/>\n" if CalendarComponents.VJOURNAL in components else "")
      }
      </C:supported-calendar-component-set>
    </D:prop>
  </D:set>
</D:mkcalendar>
"""
        print(body)
        return self._create("MKCALENDAR", url,body)

    def _extract_name_from_href(self, href) -> str:
        return href.rstrip('/').split('/')[-1]

    def delete_object(self, collection_id, filename, etag=None)->bool:
        url = path.join(self.host, self.username, collection_id, filename)
        headers = {}
        if etag:
            # WebDAV requires quoted ETags in If-Match, even if we strip them internally
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
        
        response = requests.delete(url, headers=headers, auth=(self.username, self.password))
        
        if response.status_code in [200, 204]:
            return True
        elif response.status_code == 412:
            raise PreconditionFailed(f"Delete failed: ETag mismatch for {filename}", response.status_code)
        elif response.status_code == 404:
            raise ResourceNotFound(f"Delete failed: {filename} not found", response.status_code)
        else:
            raise WebDAVError(f"Failed to delete: {response.status_code}", response.status_code, response.text)
        
    def list_collections(self)->list:
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
        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces={'DAV:': None})
        return [(c.get('href',''), get_contenttype(c)) for c in get_collections(doc) if type(c.get('propstat',{})) == dict]


    def list_calendar_objects(self, calendar_id, start: datetime = None, end: datetime = None)-> list[dict]:
        """
        Lists entries in a specific calendar, filtering by component type.
        component_type options: 'VEVENT', 'VTODO', 'VJOURNAL', None (returns all entries regardless of )
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
        <C:comp-filter name="VCALENDAR" test="anyof">
            <C:comp-filter name="VEVENT">
                {time_range_xml}
            </C:comp-filter>
            <C:comp-filter name="VTODO">
                {time_range_xml}
            </C:comp-filter>
            <C:comp-filter name="VJOURNAL">
                {time_range_xml}
            </C:comp-filter>
        </C:comp-filter>
    </C:filter>
</C:calendar-query>"""

        response = requests.request("REPORT", url, data=body, headers={"Depth": "1"}, auth=(self.username, self.password))
        
        # Parse XML and handle xmltodict's list/dict behavior for single vs multiple results
        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces={'DAV:': None})
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
            etag = props.get('getetag')
            if etag and isinstance(etag, str):
                etag = etag.strip('"')
            if cal_data:
                # Returns the full href, etag, and the raw ICS data
                results.append({'href': r.get('href'), 'etag': etag, 'data': cal_data})
        return results
    
    def list_calendar_models(self, calendar_id, start: datetime = None, end: datetime = None)-> list[tuple[Union[VEvent, VTodo, VJournal, str],str, str, str]]:
        """
        High-level getter. Retrieves and deserializes VCards and etags for an addressbook
        Returns list[tuple[[VCard_Object, etag, filename, uid]]
        """
        
        result = []
        for calendar_entry_dict in self.list_calendar_objects(calendar_id, start=start, end=end):
            etag = calendar_entry_dict['etag']
            cal_data = calendar_entry_dict['data']

            file_dir, filename = path.split(calendar_entry_dict['href'])
            uid = path.splitext(filename)[0]

            cal_object = None
            if "BEGIN:VEVENT" in cal_data:
                cal_object = VEvent.from_vcalendar_string(cal_data), etag
            elif "BEGIN:VTODO" in cal_data:
                cal_object = VTodo.from_vcalendar_string(cal_data), etag
            elif "BEGIN:VJOURNAL" in cal_data:
                cal_object = VJournal.from_vcalendar_string(cal_data), etag
            else:
                cal_object = cal_data
            result.append((cal_object, etag, filename, uid))
        return result


    def list_addressbook_entries(self, addressbook_id)-> list:
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
        
        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces={'DAV:': None})
        responses = doc.get('multistatus', {}).get('response', [])
        if isinstance(responses, dict): responses = [responses]

        results = []
        for r in responses:
            propstat = r.get('propstat', {})
            if isinstance(propstat, list): propstat = propstat[0]
            
            props = propstat.get('prop', {})
            # Check for data with matching namespace or fallback
            card_data = props.get('C:address-data', props.get('CR:address-data'))
            etag = props.get('getetag')
            if etag and isinstance(etag, str):
                etag = etag.strip('"')
            if card_data:
                results.append({'href': r.get('href'), 'etag': etag, 'data': card_data})
        return results
    
    def list_addressbook_models(self, addressbook_id)-> list[tuple[VCard,str, str, str]]:
        """
        High-level getter. Retrieves and deserializes VCards and etags for an addressbook
        Returns list[tuple[[VCard_Object, etag, filename, uid]]
        """
        result = []
        for address_entry_dict in self.list_addressbook_entries(addressbook_id):
            etag = address_entry_dict['etag']
            card_data = address_entry_dict['data']

            file_dir, filename = path.split(address_entry_dict['href'])
            uid = path.splitext(filename)[0]
            
            result.append((VCard.from_vcard_string(card_data), etag, filename, uid))
        return result

    def get_calendar_object(self, calendar_id, object_filename)->tuple[str,str]:
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
        elif response.status_code == 404:
            raise ResourceNotFound(f"Calendar object not found: {object_filename}", response.status_code)
        else:
            raise WebDAVError(f"Failed to retrieve calendar object: {response.status_code}", response.status_code, response.text)

    def get_addressbook_object(self, addressbook_id, object_filename)->tuple[str,str]:
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
        elif response.status_code == 404:
            raise ResourceNotFound(f"Contact not found: {object_filename}", response.status_code)
        else:
            raise WebDAVError(f"Failed to retrieve contact: {response.status_code}", response.status_code, response.text)
        
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

    def get_sync_token(self, collection_id: str) -> Union[str, None]:
        """
        Retrieves the current sync-token for a collection.
        """
        url = path.join(self.host, self.username, collection_id)
        body = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:sync-token/>
    </D:prop>
</D:propfind>"""
        
        response = requests.request("PROPFIND", url, data=body, headers={"Depth": "0"}, auth=(self.username, self.password))
        
        if response.status_code == 404:
            raise ResourceNotFound(f"Collection not found: {collection_id}", response.status_code)
        elif response.status_code != 207:
            return None

        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces={'DAV:': None})
        try:
            propstat = doc.get('multistatus',{}).get('response',{}).get('propstat',{})
            if isinstance(propstat, list):
                propstat = propstat[0]
            token = propstat.get('prop',{}).get('sync-token',{})
            return token
        except (AttributeError, KeyError, TypeError):
            return None

    def sync_collection(self, collection_id: str, sync_token: str = "") -> Tuple[List[Dict], List[str], str]:
        """
        Performs a WebDAV sync-collection REPORT (RFC 6578).
        Returns: (updated_items, deleted_hrefs, new_sync_token)
        updated_items is a list of dicts: {'href': str, 'etag': str}
        """
        url = path.join(self.host, self.username, collection_id)
        
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<D:sync-collection xmlns:D="DAV:">
    <D:sync-token>{sync_token}</D:sync-token>
    <D:sync-level>1</D:sync-level>
    <D:prop>
        <D:getetag/>
    </D:prop>
</D:sync-collection>"""

        response = requests.request("REPORT", url, data=body, auth=(self.username, self.password))
        
        if response.status_code == 404:
            raise ResourceNotFound(f"Collection not found: {collection_id}", response.status_code)
        elif response.status_code != 207:
            raise WebDAVError(f"Sync failed: {response.status_code}", response.status_code, response.text)

        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces={'DAV:': None})
        ms = doc.get('multistatus', {})
        new_token = ms.get('sync-token')
        
        updated = []
        deleted = []
        
        responses = ms.get('response', [])
        if isinstance(responses, dict): responses = [responses]
        
        for r in responses:
            href = r.get('href')
            status = r.get('status')
            file_dir, file_name = path.split(href)
            uid = path.splitext(file_name)[0]
            
            if status and '404' in status:
                deleted.append({'href':href, 'uid': uid, 'file_name':file_name})
            else:
                propstat = r.get('propstat', {})
                if isinstance(propstat, list): propstat = propstat[0]
                etag = propstat.get('prop', {}).get('getetag',"").strip('"')
                updated.append({'href': href, 'etag': etag, 'uid':uid, 'file_name': file_name})
                
        return updated, deleted, new_token

    def create_vcard(self, addressbook_id, vcard_obj: VCard) -> str:
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
            return filename
        else:
            raise WebDAVError(f"Failed to create vCard: {response.status_code}", response.status_code, response.text)

    def update_vcard(self, addressbook_id, filename, vcard_obj: VCard, etag=None) -> bool:
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
            return True
        elif response.status_code == 412:
            raise PreconditionFailed("Update failed: ETag mismatch", response.status_code)
        else:
            raise WebDAVError(f"Failed to update vCard: {response.status_code}", response.status_code, response.text)


    def create_calendar_object(self, calendar_id, item_obj) -> str:
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
            return filename
        else:
            raise WebDAVError(f"Failed to create object: {response.status_code}", response.status_code, response.text)

    def update_calendar_object(self, calendar_id, filename, item_obj, etag=None) -> bool:
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
            return True
        elif response.status_code == 412:
            raise PreconditionFailed("Update failed: ETag mismatch", response.status_code)
        else:
            raise WebDAVError(f"Failed to update object: {response.status_code}", response.status_code, response.text)