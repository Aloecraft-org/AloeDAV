import requests
import xmltodict
from os import path
from datetime import datetime
from pydantic import BaseModel
from logging import info, error

from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.client_util import get_multistatus_responses
from aloedav.client_util import get_ok_propfind
from aloedav.client_util import get_collection_type
from aloedav.client_util import get_href
from aloedav.model.serial_util import to_model, webdav_data
from aloedav.model.m00_constant import NS, NS_MAP, CalendarComponents
from aloedav.model.m01_base import Item
from aloedav.model.m01_collection import DAVCollection
from aloedav.model.m02_vcard import VCARD
from abc import ABC, abstractmethod

class BaseAloeDAVClient(BaseModel, ABC):
    @abstractmethod
    def create_addressbook(self, display_name, description, addressbook_id) -> bool:
        pass    
    @abstractmethod
    def create_calendar(self, display_name, description, calendar_id, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL)  -> bool:
        pass    
    @abstractmethod
    def list_collections(self) -> list[DAVCollection]:
        pass    
    @abstractmethod
    def fetch_collection(self, collection_id: str) -> DAVCollection:
        pass    
    @abstractmethod
    def sync_collection(self, collection_id: str, sync_token: str) -> dict:
        pass    
    @abstractmethod
    def fetch_object(self, collection_id, filename):
        pass    
    @abstractmethod
    def upsert_object(self, collection_id, webdav_obj: Item, etag=None) -> bool:
        pass    
    @abstractmethod
    def delete_object(self, collection_id, filename, etag=None)->bool:
        pass
    @abstractmethod
    def delete_collection(self, collection_id)->bool:
        pass
    @abstractmethod
    def list_calendar_objects(self, calendar_id, start: datetime = None, end: datetime = None)-> list[Item]:
        pass
    @abstractmethod
    def list_addressbook_objects(self, addressbook_id)-> list[VCARD]:
        pass

class AloeDAVClient(BaseAloeDAVClient):

    def __init__(self, host, username, password, request_timeout = 10, allow_delete_collection=False):
        self.host = host
        self.username = username
        self.password = password
        self.request_timeout = request_timeout
        self.allow_delete_collection = allow_delete_collection

    def _create(self, method, url, body=None) -> bool:
        TAG="[AloeDAVClient._create]"
        response = requests.request(method, url, data=body, auth=(self.username, self.password), timeout=self.request_timeout)
        
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
        return self._create("MKCALENDAR", url,body)

    def list_collections(self) -> list[DAVCollection]:
        url = path.join(self.host, self.username)
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<D:propfind {NS}>
<D:prop>
    <D:displayname/>
    <C:calendar-description/>
    <C:supported-calendar-component-set/>
    <CR:addressbook-description/>
    <D:sync-token/>
    <cs:getctag/>
    <D:resourcetype/>
    <D:getcontenttype/>
    <RADICALE:getcontentcount />
</D:prop>
</D:propfind>"""
        
        response = requests.request("PROPFIND", url, data=body, headers={"Depth": "1"}, auth=(self.username, self.password), timeout=self.request_timeout)
        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces=NS_MAP)
        return [DAVCollection.from_response(r) for r in get_multistatus_responses(doc) if get_collection_type(get_ok_propfind(r))]
    
    def fetch_collection(self, collection_id: str) -> DAVCollection:
        url = path.join(self.host, self.username, collection_id)
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<D:propfind {NS}>
    <D:prop>
        <D:displayname/>
        <C:calendar-description/>
        <C:supported-calendar-component-set/>
        <CR:addressbook-description/>
        <D:sync-token/>
        <cs:getctag/>
        <D:resourcetype/>
        <D:getcontenttype/>
        <RADICALE:getcontentcount/>
    </D:prop>
</D:propfind>"""
        
        response = requests.request("PROPFIND", url, data=body, headers={"Depth": "0"}, auth=(self.username, self.password), timeout=self.request_timeout)
        
        if response.status_code == 404:
            raise ResourceNotFound(f"Collection not found: {collection_id}", response.status_code)
        elif response.status_code != 207:
            return None

        doc = xmltodict.parse(response.content, process_namespaces=True, namespaces=NS_MAP)
        return next(DAVCollection.from_response(r) for r in get_multistatus_responses(doc))
    
    def sync_collection(self, collection_id: str, sync_token: str) -> dict:
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
        new_token = doc.get('multistatus', {}).get('sync-token', None)
        responses = get_multistatus_responses(doc)
        if isinstance(responses, dict): responses = [responses]
        
        updated = []
        deleted = []
        
        for r in responses:
            href = get_href(r)
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
                
        return {
            "deleted":deleted, 
            "updated":updated, 
            "sync_token": new_token
        }
    
    def fetch_object(self, collection_id, filename) -> list[Item]:
        response = requests.get(
            url=path.join(self.host, self.username, collection_id, filename), 
            auth=(self.username, self.password), 
            timeout=self.request_timeout)
        if response.status_code == 200:
            return to_model(response.text, response.headers.get("ETag", None))
        elif response.status_code == 404:
            raise ResourceNotFound(f"Contact not found: {collection_id}", response.status_code)
        else:
            raise WebDAVError(f"Failed to retrieve object: {response.status_code}", response.status_code, response.text)

    def upsert_object(self, collection_id, webdav_obj: Item, etag=None) -> Item:
        webdav_data = webdav_obj.to_webdav_string()
        filename = webdav_obj.filename()
        headers = {"Content-Type": webdav_obj.content_type}
        if etag:
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
            
        response = requests.put(
            url=path.join(self.host, self.username, collection_id, filename),
            data=webdav_data.encode('utf-8'), 
            headers=headers, auth=(self.username, self.password),
            timeout=self.request_timeout)

        if response.status_code in [200, 201, 204]:
            etag = response.headers.get("ETag", "").strip('"')
            webdav_obj.etag = etag
            return webdav_obj
        elif response.status_code == 412:
            raise PreconditionFailed("Upsert failed: ETag mismatch", response.status_code)
        else:
            raise WebDAVError(f"Failed to upsert object: {response.status_code}", response.status_code, response.text)

    def delete_object(self, collection_id, filename, etag=None)->bool:
        url = path.join(self.host, self.username, collection_id, filename)
        headers = {}
        if etag:
            # WebDAV requires quoted ETags in If-Match, even if we strip them internally
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
        
        response = requests.delete(url, headers=headers, auth=(self.username, self.password), timeout=self.request_timeout)
        
        if response.status_code in [200, 204]:
            return True
        elif response.status_code == 412:
            raise PreconditionFailed(f"Delete failed: ETag mismatch for {filename}", response.status_code)
        elif response.status_code == 404:
            raise ResourceNotFound(f"Delete failed: {filename} not found", response.status_code)
        else:
            raise WebDAVError(f"Failed to delete: {response.status_code}", response.status_code, response.text)
        
    def delete_collection(self, collection_id)->bool:
        if not self.allow_delete_collection:
            raise AloeDAVClientError("AloeDAVClient must be created with allow_delete_collection to allow deleting collections")
        
        url = path.join(self.host, self.username, collection_id)
        headers = {}
        
        response = requests.delete(url, headers=headers, auth=(self.username, self.password), timeout=self.request_timeout)
        
        if response.status_code in [200, 204]:
            return True
        elif response.status_code == 404:
            raise ResourceNotFound(f"Delete failed: {collection_id} not found", response.status_code)
        else:
            raise WebDAVError(f"Failed to delete: {response.status_code}", response.status_code, response.text)


    def list_calendar_objects(self, calendar_id, start: datetime = None, end: datetime = None)-> list[Item]:
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
            if isinstance(propstat, list): propstat = propstat[0]
            props = propstat.get('prop', {})
            cal_data = props.get('calendar-data')
            etag = props.get('getetag', '').strip('"')
            item = to_model(cal_data, etag)
            results.extend(item)
        return results

    def list_addressbook_objects(self, addressbook_id)-> list[VCARD]:
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
            card_data = props.get('address-data')
            etag = props.get('getetag', '').strip('"')
            item = to_model(card_data, etag)
            results.extend(item)
        return results