import requests
import xmltodict
from os import path
from datetime import datetime
from pydantic import BaseModel
from logging import info, error
from urllib.parse import quote, unquote
from xml.sax.saxutils import escape as xml_escape

from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.client_util import get_multistatus_responses
from aloedav.client_util import get_ok_propfind
from aloedav.client_util import get_collection_type
from aloedav.client_util import get_href
from aloedav.model.serial_util import to_model, to_resource, webdav_data
from aloedav.model.m00_constant import NS, NS_MAP, CalendarComponents
from aloedav.model.m01_base import Item
from aloedav.model.m01_collection import DAVCollection
from aloedav.model.m02_vcard import VCARD
from abc import ABC, abstractmethod

class BaseAloeDAVClient(ABC):
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

    def _url(self, *segments) -> str:
        """
        Builds a request URL from path segments.

        os.path.join is not safe here: it is platform dependent, it discards
        everything to the left of a segment that starts with '/', and it leaves
        reserved characters unencoded so that a UID containing '#' or a space
        silently addresses the wrong resource.
        """
        encoded = [quote(str(s).strip("/"), safe="") for s in segments if s not in (None, "")]
        return "/".join([self.host.rstrip("/")] + encoded)

    def _request(self, method, url, body=None, headers=None) -> requests.Response:
        """
        Issues a request with the client's credentials and timeout. Every call
        goes through here so that no request can be left unbounded.
        """
        return requests.request(
            method, url, data=body, headers=headers,
            auth=(self.username, self.password),
            timeout=self.request_timeout)

    def _multistatus(self, response, context, namespaces=None) -> dict:
        """
        Validates a 207 Multi-Status response and parses its body.

        A non-207 must not fall through to the parser: an error page yields no
        <multistatus> element, which would otherwise be reported as an empty
        collection and make a rejected request indistinguishable from an
        account with nothing in it.
        """
        if response.status_code == 401:
            raise AuthenticationError(f"Authentication failed for {context}", response.status_code, response.text)
        elif response.status_code == 404:
            raise ResourceNotFound(f"Not found: {context}", response.status_code, response.text)
        elif response.status_code != 207:
            raise WebDAVError(f"{context} failed: {response.status_code}", response.status_code, response.text)

        return xmltodict.parse(
            response.content, process_namespaces=True,
            namespaces=NS_MAP if namespaces is None else namespaces)

    def _extract_objects(self, doc, data_key) -> list[Item]:
        """
        Collects the parsed objects out of a REPORT Multi-Status body.

        The propstat carrying the data is the one with a 200 status; a response
        may also carry a 404 propstat for properties the server does not hold,
        and picking that one blindly loses the entry.
        """
        results = []
        for r in get_multistatus_responses(doc):
            props = get_ok_propfind(r)
            data = props.get(data_key)
            if not data:
                continue
            etag = (props.get('getetag') or '').strip('"')
            results.extend(to_model(data, etag))
        return results

    def _create(self, method, url, body=None) -> bool:
        TAG="[AloeDAVClient._create]"
        response = self._request(method, url, body)
        
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
        url = self._url(self.username, addressbook_id)
        body=f"""<?xml version="1.0" encoding="UTF-8" ?>
<D:mkcol xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:set>
    <D:prop>
      <D:displayname>{xml_escape(display_name or "")}</D:displayname>
      <C:addressbook-description>{xml_escape(description or "")}</C:addressbook-description>
      <D:resourcetype>
        <D:collection/>
        <C:addressbook/>
      </D:resourcetype>
    </D:prop>
  </D:set>
</D:mkcol>"""
        return self._create("MKCOL", url, body)
    
    def create_calendar(self, display_name, description, calendar_id, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL)  -> bool:
        url = self._url(self.username, calendar_id)
        body=f"""<?xml version="1.0" encoding="UTF-8" ?>
<D:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:set>
    <D:prop>
      <D:displayname>{xml_escape(display_name or "")}</D:displayname>
      <C:calendar-description>{xml_escape(description or "")}</C:calendar-description>
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
        url = self._url(self.username)
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
        
        response = self._request("PROPFIND", url, body, headers={"Depth": "1"})
        doc = self._multistatus(response, "List collections")
        return [DAVCollection.from_response(r) for r in get_multistatus_responses(doc) if get_collection_type(get_ok_propfind(r))]
    
    def fetch_collection(self, collection_id: str) -> DAVCollection:
        url = self._url(self.username, collection_id)
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
        
        response = self._request("PROPFIND", url, body, headers={"Depth": "0"})
        doc = self._multistatus(response, f"Collection {collection_id}")
        return next((DAVCollection.from_response(r) for r in get_multistatus_responses(doc)), None)
    
    def sync_collection(self, collection_id: str, sync_token: str) -> dict:
        """
        Performs a WebDAV sync-collection REPORT (RFC 6578).
        Returns: (updated_items, deleted_hrefs, new_sync_token)
        updated_items is a list of dicts: {'href': str, 'etag': str}
        """
        url = self._url(self.username, collection_id)
        
        # An absent token means "initial sync": the element must be empty rather
        # than carry the literal string "None".
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<D:sync-collection xmlns:D="DAV:">
    <D:sync-token>{xml_escape(sync_token) if sync_token else ""}</D:sync-token>
    <D:sync-level>1</D:sync-level>
    <D:prop>
        <D:getetag/>
    </D:prop>
</D:sync-collection>"""

        response = self._request("REPORT", url, body)
        doc = self._multistatus(response, f"Sync {collection_id}", namespaces={'DAV:': None})
        new_token = doc.get('multistatus', {}).get('sync-token', None)
        responses = get_multistatus_responses(doc)

        updated = []
        deleted = []

        for r in responses:
            href = unquote(get_href(r))
            status = r.get('status')
            file_dir, file_name = path.split(href)
            uid = path.splitext(file_name)[0]

            if status and '404' in status:
                deleted.append({'href':href, 'uid': uid, 'file_name':file_name})
            else:
                etag = (get_ok_propfind(r).get('getetag') or "").strip('"')
                updated.append({'href': href, 'etag': etag, 'uid':uid, 'file_name': file_name})
                
        return {
            "deleted":deleted, 
            "updated":updated, 
            "sync_token": new_token
        }
    
    def fetch_object(self, collection_id, filename) -> list[Item]:
        response = self._request("GET", self._url(self.username, collection_id, filename))
        if response.status_code == 200:
            return to_model(response.text, response.headers.get("ETag", None))
        elif response.status_code == 404:
            raise ResourceNotFound(f"Contact not found: {collection_id}", response.status_code)
        else:
            raise WebDAVError(f"Failed to retrieve object: {response.status_code}", response.status_code, response.text)

    def fetch_resource(self, collection_id, filename):
        """
        Fetches one resource whole, keeping a recurring master and its
        RECURRENCE-ID overrides together. Prefer this over fetch_object when
        the result will be written back: fetch_object returns the components
        individually, and writing one back drops its siblings.
        """
        response = self._request("GET", self._url(self.username, collection_id, filename))
        if response.status_code == 200:
            return to_resource(response.text, response.headers.get("ETag", "").strip('"') or None)
        elif response.status_code == 404:
            raise ResourceNotFound(f"Object not found: {collection_id}/{filename}", response.status_code)
        else:
            raise WebDAVError(f"Failed to retrieve object: {response.status_code}", response.status_code, response.text)

    def upsert_object(self, collection_id, webdav_obj, etag=None):
        """
        Writes one resource. Accepts either a Resource or a bare Item; both
        expose filename()/content_type/to_webdav_string(), and a Resource is
        the safer input because it carries every component of the resource.
        """
        webdav_data = webdav_obj.to_webdav_string()
        filename = webdav_obj.filename()
        headers = {"Content-Type": webdav_obj.content_type}
        if etag:
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
            
        response = self._request(
            "PUT", self._url(self.username, collection_id, filename),
            body=webdav_data.encode('utf-8'), headers=headers)

        if response.status_code in [200, 201, 204]:
            etag = response.headers.get("ETag", "").strip('"')
            webdav_obj.etag = etag
            return webdav_obj
        elif response.status_code == 412:
            raise PreconditionFailed("Upsert failed: ETag mismatch", response.status_code)
        else:
            raise WebDAVError(f"Failed to upsert object: {response.status_code}", response.status_code, response.text)

    def delete_object(self, collection_id, filename, etag=None)->bool:
        url = self._url(self.username, collection_id, filename)
        headers = {}
        if etag:
            # WebDAV requires quoted ETags in If-Match, even if we strip them internally
            headers["If-Match"] = f'"{etag}"' if not etag.startswith('"') else etag
        
        response = self._request("DELETE", url, headers=headers)
        
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
        
        url = self._url(self.username, collection_id)
        headers = {}
        
        response = self._request("DELETE", url, headers=headers)
        
        if response.status_code in [200, 204]:
            return True
        elif response.status_code == 404:
            raise ResourceNotFound(f"Delete failed: {collection_id} not found", response.status_code)
        else:
            raise WebDAVError(f"Failed to delete: {response.status_code}", response.status_code, response.text)


    def list_calendar_objects(self, calendar_id, start: datetime = None, end: datetime = None)-> list[Item]:
        url = self._url(self.username, calendar_id)
        
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
 
        response = self._request("REPORT", url, body, headers={"Depth": "1"})
        # Every namespace is stripped, not just DAV:. The data being asked for
        # lives in the CalDAV namespace, so a parse that only collapsed DAV:
        # left the key as "urn:...:caldav:calendar-data" and the lookup below
        # never matched -- this REPORT always came back empty.
        doc = self._multistatus(response, f"List objects in {calendar_id}")
        return self._extract_objects(doc, 'calendar-data')

    def list_addressbook_objects(self, addressbook_id)-> list[VCARD]:
        """
        Lists all vCards in a specific addressbook.
        """
        url = self._url(self.username, addressbook_id)
        body = """<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
    <D:prop>
        <D:getetag/>
        <C:address-data/>
    </D:prop>
</C:addressbook-query>"""
 
        response = self._request("REPORT", url, body, headers={"Depth": "1"})
        # As above: address-data is in the CardDAV namespace.
        doc = self._multistatus(response, f"List objects in {addressbook_id}")
        return self._extract_objects(doc, 'address-data')