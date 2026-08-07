import unittest
import xml.dom.minidom
from unittest.mock import patch

from aloedav.client import AloeDAVClient
from aloedav.client_util import get_ok_propfind, get_collection_type, get_multistatus_responses
from aloedav.collection import CollectionType
from aloedav.collection.local_collection import LocalCollection
from aloedav.collection.remote_collection import RemoteCollection
from aloedav.exceptions import AuthenticationError, PreconditionFailed, WebDAVError
from aloedav.model.m00_constant import NS_MAP
from aloedav.model.m02_vcard import VCARD

import xmltodict


class FakeResponse:
    def __init__(self, status_code=207, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", "replace") if isinstance(content, bytes) else str(content)
        self.headers = headers or {}


def capturing_client(response, **kwargs):
    """
    Returns (client, captured) where captured records the outgoing request.
    """
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, body=kw.get("data"),
                        headers=kw.get("headers"), timeout=kw.get("timeout"))
        return response

    client = AloeDAVClient("https://dav.example.com/", "user", "pw", **kwargs)
    return client, captured, fake_request


MULTISTATUS_ONE_COLLECTION = b"""<?xml version="1.0"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
 <response>
  <href>/user/work/</href>
  <propstat>
   <prop>
    <displayname>Work</displayname>
    <resourcetype><collection/><C:calendar/></resourcetype>
   </prop>
   <status>HTTP/1.1 200 OK</status>
  </propstat>
 </response>
</multistatus>"""


class TestRequestBuilding(unittest.TestCase):

    def test_urls_are_percent_encoded(self):
        client = AloeDAVClient("https://dav.example.com/", "user", "pw")
        self.assertEqual(client._url("user", "cal", "abc.ics"),
                         "https://dav.example.com/user/cal/abc.ics")
        self.assertEqual(client._url("user", "cal", "a#b.ics"),
                         "https://dav.example.com/user/cal/a%23b.ics")
        self.assertEqual(client._url("user", "cal", "a b.ics"),
                         "https://dav.example.com/user/cal/a%20b.ics")

    def test_absolute_segment_cannot_escape_the_host(self):
        client = AloeDAVClient("https://dav.example.com/", "user", "pw")
        url = client._url("user", "/etc/passwd")
        self.assertTrue(url.startswith("https://dav.example.com/"),
                        f"segment escaped the host: {url}")

    def test_every_request_carries_a_timeout(self):
        response = FakeResponse(207, MULTISTATUS_ONE_COLLECTION)
        client, captured, fake = capturing_client(response, request_timeout=7)
        with patch("aloedav.client.requests.request", fake):
            client.list_collections()
        self.assertEqual(captured["timeout"], 7)

    def test_collection_names_are_xml_escaped(self):
        client, captured, fake = capturing_client(FakeResponse(201))
        with patch("aloedav.client.requests.request", fake):
            client.create_calendar("Tom & Jerry <Work>", "R&D", "cal1")
        # Must parse; an unescaped ampersand would raise here.
        xml.dom.minidom.parseString(captured["body"])
        self.assertIn("Tom &amp; Jerry &lt;Work&gt;", captured["body"])

    def test_addressbook_names_are_xml_escaped(self):
        client, captured, fake = capturing_client(FakeResponse(201))
        with patch("aloedav.client.requests.request", fake):
            client.create_addressbook("A & B", "x < y", "ab1")
        xml.dom.minidom.parseString(captured["body"])

    def test_initial_sync_sends_an_empty_token(self):
        body = b"""<?xml version="1.0"?>
<multistatus xmlns="DAV:"><sync-token>tok-1</sync-token></multistatus>"""
        client, captured, fake = capturing_client(FakeResponse(207, body))
        with patch("aloedav.client.requests.request", fake):
            client.sync_collection("cal1", None)
        self.assertIn("<D:sync-token></D:sync-token>", captured["body"])
        self.assertNotIn("None", captured["body"])


class TestErrorSignalling(unittest.TestCase):
    """
    A rejected request must not be reported as an empty collection.
    """

    def test_list_collections_raises_on_401(self):
        client, _, fake = capturing_client(FakeResponse(401, b"nope"))
        with patch("aloedav.client.requests.request", fake):
            with self.assertRaises(AuthenticationError):
                client.list_collections()

    def test_list_calendar_objects_raises_on_401(self):
        client, _, fake = capturing_client(FakeResponse(401, b"nope"))
        with patch("aloedav.client.requests.request", fake):
            with self.assertRaises(AuthenticationError):
                client.list_calendar_objects("cal1")

    def test_list_addressbook_objects_raises_on_401(self):
        client, _, fake = capturing_client(FakeResponse(401, b"nope"))
        with patch("aloedav.client.requests.request", fake):
            with self.assertRaises(AuthenticationError):
                client.list_addressbook_objects("ab1")

    def test_list_collections_raises_on_500(self):
        client, _, fake = capturing_client(FakeResponse(500, b"boom"))
        with patch("aloedav.client.requests.request", fake):
            with self.assertRaises(WebDAVError):
                client.list_collections()


class TestResponseParsing(unittest.TestCase):

    def parse(self, xml_bytes):
        return xmltodict.parse(xml_bytes, process_namespaces=True, namespaces=NS_MAP)

    def test_single_propstat_is_handled(self):
        # xmltodict collapses a lone propstat to a dict rather than a list.
        doc = self.parse(MULTISTATUS_ONE_COLLECTION)
        response = get_multistatus_responses(doc)[0]
        prop = get_ok_propfind(response)
        self.assertEqual(prop.get("displayname"), "Work")

    def test_ok_propstat_is_selected_over_a_404_propstat(self):
        body = b"""<?xml version="1.0"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
 <response>
  <href>/user/work/</href>
  <propstat>
   <prop><getcontentcount/></prop>
   <status>HTTP/1.1 404 Not Found</status>
  </propstat>
  <propstat>
   <prop><displayname>Work</displayname>
    <resourcetype><collection/><C:calendar/></resourcetype></prop>
   <status>HTTP/1.1 200 OK</status>
  </propstat>
 </response>
</multistatus>"""
        response = get_multistatus_responses(self.parse(body))[0]
        self.assertEqual(get_ok_propfind(response).get("displayname"), "Work")

    def test_missing_resourcetype_is_not_a_crash(self):
        self.assertIsNone(get_collection_type({}))
        self.assertIsNone(get_collection_type({"resourcetype": None}))

    def test_list_collections_parses_a_single_propstat_response(self):
        client, _, fake = capturing_client(FakeResponse(207, MULTISTATUS_ONE_COLLECTION))
        with patch("aloedav.client.requests.request", fake):
            collections = client.list_collections()
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0].displayname, "Work")
        self.assertEqual(collections[0].collection_id, "work")
        self.assertEqual(collections[0].user, "user")

    def test_collection_id_resolves_under_a_mount_prefix(self):
        body = MULTISTATUS_ONE_COLLECTION.replace(b"/user/work/", b"/dav/user/work/")
        client, _, fake = capturing_client(FakeResponse(207, body))
        with patch("aloedav.client.requests.request", fake):
            collections = client.list_collections()
        self.assertEqual(collections[0].collection_id, "work")
        self.assertEqual(collections[0].user, "user")


class TestRemoteCollectionWiring(unittest.TestCase):
    """
    These methods were unreachable in the original: each one raised before
    doing any work. The checks are deliberately shallow -- they assert the
    call reaches the client at all.
    """

    def build(self, client=None):
        return RemoteCollection.model_construct(
            client=client or AloeDAVClient("https://dav.example.com/", "u", "p"),
            uid="cal1", href="", ctag="", synctoken="", contentcount="",
            displayname="Cal", description="", component_set=None,
            collection_type=CollectionType.CALENDAR, items={})

    def test_delete_item_reaches_the_client(self):
        collection = self.build()
        with patch.object(collection.client, "delete_object", return_value=True) as spy:
            self.assertTrue(collection.delete_item("a.ics", etag="e1"))
        spy.assert_called_once_with("cal1", "a.ics", "e1")

    def test_get_item_returns_the_first_object(self):
        collection = self.build()
        card = VCARD(uid="c1", fn="Alice")
        with patch.object(collection.client, "fetch_object", return_value=[card]):
            self.assertIs(collection.get_item("c1.vcf"), card)

    def test_list_items_rejects_an_unknown_collection_type(self):
        collection = self.build()
        collection.collection_type = None
        with self.assertRaises(Exception) as ctx:
            collection.list_items()
        self.assertNotIsInstance(ctx.exception, TypeError)

    def test_refresh_assigns_scalars_not_tuples(self):
        collection = self.build()

        class Fetched:
            href, ctag, synctoken, contentcount = "/u/cal1/", "ctag-1", "tok-1", "3"
            displayname, description = "Cal", "desc"
            component_set, collection_type = None, CollectionType.CALENDAR

        with patch.object(collection.client, "fetch_collection", return_value=Fetched()):
            self.assertEqual(collection.refresh_sync_token(), "tok-1")

        for field in ("href", "ctag", "synctoken", "contentcount", "displayname", "description"):
            value = getattr(collection, field)
            self.assertNotIsInstance(value, tuple, f"{field} was assigned a tuple")


class TestLocalCollectionConcurrency(unittest.TestCase):

    def setUp(self):
        self.collection = LocalCollection.create_addressbook("AB", "desc", "ab1")
        self.filename, self.etag = self.collection.insert_item(VCARD(uid="c1", fn="Alice"))

    def test_stale_etag_is_rejected(self):
        update = VCARD(uid="c1", fn="Alice Updated")
        update.etag = "STALE"
        with self.assertRaises(PreconditionFailed):
            self.collection.update_item(self.filename, update, etag="STALE")

    def test_current_etag_is_accepted(self):
        update = VCARD(uid="c1", fn="Alice Updated")
        new_etag = self.collection.update_item(self.filename, update, etag=self.etag)
        self.assertNotEqual(new_etag, self.etag)
        self.assertEqual(self.collection.get_item(self.filename).full_name, "Alice Updated")

    def test_no_etag_skips_the_check(self):
        update = VCARD(uid="c1", fn="Alice Updated")
        self.collection.update_item(self.filename, update)
        self.assertEqual(self.collection.get_item(self.filename).full_name, "Alice Updated")


if __name__ == "__main__":
    unittest.main()
