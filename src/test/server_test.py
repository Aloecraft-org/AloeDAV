"""
Protocol tests.

These check what goes on the wire, because that is the whole contract: a client
sees status codes, headers and XML, and nothing else. Where a status is
load-bearing -- 412 for a failed precondition, 403 with DAV:valid-sync-token,
404 for a deleted resource inside a sync report -- it is asserted specifically,
since answering 200 with an empty body instead would leave a client believing
something happened.
"""
import re
import shutil
import tempfile
import unittest

from starlette.testclient import TestClient

from aloedav.collection import CollectionType
from aloedav.model.serial_util import to_resource
from aloedav.server import create_app
from aloedav.server.auth import FileAuthenticator, OpenAuthenticator
from aloedav.storage.backends import open_store

NY = "America/New_York"
AUTH = ("alice", "pw")

D = 'xmlns:D="DAV:"'
C = 'xmlns:C="urn:ietf:params:xml:ns:caldav"'
CR = 'xmlns:CR="urn:ietf:params:xml:ns:carddav"'

SERIES = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VTIMEZONE", "TZID:America/New_York", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:standup@x", "SUMMARY:Standup",
    f"DTSTART;TZID={NY}:20260302T090000",
    "RRULE:FREQ=WEEKLY;COUNT=4", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@x",
    f"RECURRENCE-ID;TZID={NY}:20260309T090000",
    f"DTSTART;TZID={NY}:20260309T110000",
    "SUMMARY:Standup moved", "END:VEVENT",
    "END:VCALENDAR"])

JULY = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:july@x", "SUMMARY:Summer party",
    "DTSTART:20260714T180000Z", "END:VEVENT", "END:VCALENDAR"])

CARD = "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", "UID:ada@x",
                    "FN:Ada Lovelace", "N:Lovelace;Ada;;;", "END:VCARD"])


def hrefs(response) -> list[str]:
    return re.findall(r"<D:href>([^<]*)</D:href>", response.text)


class ServerTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = open_store(self.root)
        self.addCleanup(self.store.close)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

        # A low cost keeps the suite quick; the default is unaffected.
        self.auth = FileAuthenticator(self.root + "/users.json", iterations=1000)
        self.auth.add_user("alice", "pw")
        self.store.create_collection("alice", "work", CollectionType.CALENDAR, "Work", "desc")
        self.store.put_resource("alice", "work", to_resource(SERIES))
        self.client = TestClient(create_app(self.store, self.auth))

    def dav(self, method, path, body=None, depth=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if depth is not None:
            headers["Depth"] = depth
        return self.client.request(method, path, auth=kwargs.pop("auth", AUTH),
                                   content=body.encode() if body else None,
                                   headers=headers, **kwargs)

    def propfind(self, path, props_xml, depth="0"):
        body = (f'<?xml version="1.0"?><D:propfind {D} {C} {CR}>'
                f"<D:prop>{props_xml}</D:prop></D:propfind>")
        return self.dav("PROPFIND", path, body, depth=depth)


class TestAuthentication(ServerTest):

    def test_unauthenticated_is_challenged(self):
        response = self.client.request("PROPFIND", "/")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response.headers["WWW-Authenticate"])

    def test_wrong_password_is_refused(self):
        self.assertEqual(
            self.client.request("PROPFIND", "/", auth=("alice", "wrong")).status_code, 401)

    def test_unknown_user_is_refused(self):
        self.assertEqual(
            self.client.request("PROPFIND", "/", auth=("mallory", "pw")).status_code, 401)

    def test_options_needs_no_credentials(self):
        # A client sends OPTIONS before it has anywhere to put credentials;
        # challenging here makes some of them abandon account setup.
        response = self.client.request("OPTIONS", "/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("calendar-access", response.headers["DAV"])

    def test_another_users_tree_is_refused(self):
        self.store.create_collection("bob", "cal", CollectionType.CALENDAR)
        self.assertEqual(self.dav("PROPFIND", "/bob/").status_code, 403)
        self.assertEqual(self.dav("GET", "/bob/cal/x.ics").status_code, 403)


class TestCapabilities(ServerTest):

    def test_options_advertises_the_extensions(self):
        header = self.dav("OPTIONS", "/alice/work/").headers["DAV"]
        for token in ("1", "2", "3", "calendar-access", "addressbook"):
            self.assertIn(token, header)

    def test_options_lists_the_methods(self):
        allow = self.dav("OPTIONS", "/alice/work/").headers["Allow"]
        for method in ("PROPFIND", "REPORT", "PUT", "DELETE", "MKCALENDAR"):
            self.assertIn(method, allow)

    def test_dav_header_is_on_every_response(self):
        # Clients check this on more than OPTIONS.
        self.assertIn("DAV", self.dav("GET", "/alice/work/standup@x.ics").headers)

    def test_unknown_method_is_refused(self):
        self.assertEqual(self.dav("PATCH", "/alice/work/").status_code, 405)


class TestDiscovery(ServerTest):

    def test_well_known_caldav_redirects(self):
        response = self.client.get("/.well-known/caldav", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "/")

    def test_well_known_carddav_redirects(self):
        self.assertEqual(
            self.client.get("/.well-known/carddav", follow_redirects=False).status_code, 301)

    def test_root_reports_the_current_user_principal(self):
        response = self.propfind("/", "<D:current-user-principal/>")
        self.assertEqual(response.status_code, 207)
        self.assertIn("/alice/", hrefs(response))

    def test_principal_reports_both_home_sets(self):
        response = self.propfind(
            "/alice/", "<C:calendar-home-set/><CR:addressbook-home-set/>")
        self.assertIn("calendar-home-set", response.text)
        self.assertIn("addressbook-home-set", response.text)

    def test_principal_is_marked_as_one(self):
        response = self.propfind("/alice/", "<D:resourcetype/>")
        self.assertIn("principal", response.text)

    def test_supported_reports_are_advertised(self):
        response = self.propfind("/alice/work/", "<D:supported-report-set/>")
        for report in ("sync-collection", "calendar-query", "calendar-multiget"):
            self.assertIn(report, response.text)


class TestPropfind(ServerTest):

    def test_principal_depth_one_lists_collections(self):
        response = self.propfind("/alice/", "<D:resourcetype/>", depth="1")
        self.assertIn("/alice/work/", hrefs(response))

    def test_collection_depth_one_lists_resources(self):
        response = self.propfind("/alice/work/", "<D:getetag/>", depth="1")
        self.assertIn("/alice/work/standup%40x.ics", hrefs(response))

    def test_collection_depth_zero_does_not_list_resources(self):
        response = self.propfind("/alice/work/", "<D:getetag/>", depth="0")
        self.assertEqual(hrefs(response), ["/alice/work/"])

    def test_collection_reports_its_type(self):
        response = self.propfind("/alice/work/", "<D:resourcetype/>")
        self.assertIn("calendar", response.text)

    def test_addressbook_reports_its_type(self):
        self.store.create_collection("alice", "people", CollectionType.ADDRESSBOOK, "P")
        response = self.propfind("/alice/people/", "<D:resourcetype/>")
        self.assertIn("addressbook", response.text)

    def test_ctag_and_sync_token_are_reported(self):
        response = self.propfind(
            "/alice/work/", '<CS:getctag xmlns:CS="http://calendarserver.org/ns/"/><D:sync-token/>')
        self.assertIn("getctag", response.text)
        self.assertIn("sync-token", response.text)

    def test_component_set_is_reported(self):
        response = self.propfind("/alice/work/", "<C:supported-calendar-component-set/>")
        self.assertIn('name="VEVENT"', response.text)

    def test_unknown_property_is_reported_as_404(self):
        # Silence would be indistinguishable from the server ignoring the ask.
        response = self.propfind("/alice/work/", "<D:no-such-property/>")
        self.assertIn("404 Not Found", response.text)
        self.assertIn("no-such-property", response.text)

    def test_resource_reports_etag_and_content_type(self):
        response = self.propfind("/alice/work/standup@x.ics",
                                 "<D:getetag/><D:getcontenttype/>")
        self.assertIn("text/calendar", response.text)
        self.assertRegex(response.text, r"<D:getetag>&quot;|<D:getetag>\"")

    def test_missing_collection_is_404(self):
        self.assertEqual(self.propfind("/alice/nope/", "<D:getetag/>").status_code, 404)

    def test_missing_resource_is_404(self):
        self.assertEqual(
            self.propfind("/alice/work/nope.ics", "<D:getetag/>").status_code, 404)

    def test_malformed_body_is_400(self):
        self.assertEqual(self.dav("PROPFIND", "/alice/work/", "<not xml").status_code, 400)

    def test_allprop_omits_calendar_data(self):
        # Inlining every body into a listing would make a routine poll enormous.
        response = self.dav("PROPFIND", "/alice/work/",
                            f'<?xml version="1.0"?><D:propfind {D}><D:allprop/></D:propfind>',
                            depth="1")
        self.assertNotIn("BEGIN:VCALENDAR", response.text)


class TestGetPutDelete(ServerTest):

    def etag_of(self, path="/alice/work/standup@x.ics"):
        return self.dav("GET", path).headers["ETag"]

    def test_get_returns_the_stored_bytes(self):
        response = self.dav("GET", "/alice/work/standup@x.ics")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith("BEGIN:VCALENDAR"))
        self.assertIn("RECURRENCE-ID", response.text)

    def test_get_quotes_the_etag(self):
        self.assertTrue(self.etag_of().startswith('"'))

    def test_head_has_no_body_but_the_same_headers(self):
        head = self.dav("HEAD", "/alice/work/standup@x.ics")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.text, "")
        self.assertEqual(head.headers["ETag"], self.etag_of())

    def test_if_none_match_returns_304(self):
        response = self.dav("GET", "/alice/work/standup@x.ics",
                            headers={"If-None-Match": self.etag_of()})
        self.assertEqual(response.status_code, 304)

    def test_get_missing_is_404(self):
        self.assertEqual(self.dav("GET", "/alice/work/nope.ics").status_code, 404)

    def test_get_on_a_collection_is_405(self):
        self.assertEqual(self.dav("GET", "/alice/work/").status_code, 405)

    def test_put_creates(self):
        response = self.dav("PUT", "/alice/work/july@x.ics", JULY)
        self.assertEqual(response.status_code, 201)
        self.assertIn("ETag", response.headers)

    def test_put_updates_with_a_matching_etag(self):
        etag = self.etag_of()
        response = self.dav("PUT", "/alice/work/standup@x.ics",
                            SERIES.replace("Standup", "Renamed"),
                            headers={"If-Match": etag})
        self.assertEqual(response.status_code, 204)

    def test_put_with_a_stale_etag_is_412(self):
        response = self.dav("PUT", "/alice/work/standup@x.ics", JULY,
                            headers={"If-Match": '"stale"'})
        self.assertEqual(response.status_code, 412)

    def test_if_none_match_star_refuses_an_overwrite(self):
        response = self.dav("PUT", "/alice/work/standup@x.ics", JULY,
                            headers={"If-None-Match": "*"})
        self.assertEqual(response.status_code, 412)

    def test_put_of_unparseable_data_is_refused(self):
        response = self.dav("PUT", "/alice/work/bad.ics", "this is not a calendar")
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid-calendar-data", response.text)

    def test_put_into_a_missing_collection_is_409(self):
        self.assertEqual(self.dav("PUT", "/alice/nope/x.ics", JULY).status_code, 409)

    def test_put_preserves_the_series(self):
        self.dav("PUT", "/alice/work/round@x.ics", SERIES.replace("standup@x", "round@x"))
        resource = self.store.get_resource("alice", "work", "round@x.ics")
        self.assertEqual(len(resource.components), 2)
        self.assertEqual(resource.master.dtstart.tzid, NY)

    def test_delete_removes_the_resource(self):
        self.assertEqual(self.dav("DELETE", "/alice/work/standup@x.ics").status_code, 204)
        self.assertEqual(self.dav("GET", "/alice/work/standup@x.ics").status_code, 404)

    def test_delete_with_a_stale_etag_is_412(self):
        response = self.dav("DELETE", "/alice/work/standup@x.ics",
                            headers={"If-Match": '"stale"'})
        self.assertEqual(response.status_code, 412)

    def test_delete_missing_is_404(self):
        self.assertEqual(self.dav("DELETE", "/alice/work/nope.ics").status_code, 404)

    def test_delete_a_collection(self):
        self.assertEqual(self.dav("DELETE", "/alice/work/").status_code, 204)
        self.assertEqual(self.store.list_collections("alice"), [])


class TestMakeCollection(ServerTest):

    def test_mkcalendar_creates_a_calendar(self):
        body = (f'<?xml version="1.0"?><C:mkcalendar {D} {C}><D:set><D:prop>'
                "<D:displayname>New</D:displayname>"
                '<C:supported-calendar-component-set><C:comp name="VEVENT"/>'
                "</C:supported-calendar-component-set>"
                "</D:prop></D:set></C:mkcalendar>")
        self.assertEqual(self.dav("MKCALENDAR", "/alice/new/", body).status_code, 201)
        info = self.store.get_collection("alice", "new")
        self.assertEqual(info.displayname, "New")
        self.assertIs(info.collection_type, CollectionType.CALENDAR)

    def test_mkcol_creates_an_addressbook_when_asked(self):
        body = (f'<?xml version="1.0"?><D:mkcol {D} {CR}><D:set><D:prop>'
                "<D:displayname>People</D:displayname>"
                "<D:resourcetype><D:collection/><CR:addressbook/></D:resourcetype>"
                "</D:prop></D:set></D:mkcol>")
        self.assertEqual(self.dav("MKCOL", "/alice/people/", body).status_code, 201)
        self.assertIs(self.store.get_collection("alice", "people").collection_type,
                      CollectionType.ADDRESSBOOK)

    def test_making_an_existing_collection_is_refused(self):
        response = self.dav("MKCALENDAR", "/alice/work/")
        self.assertEqual(response.status_code, 405)
        self.assertIn("resource-must-be-null", response.text)

    def test_mkcol_on_a_resource_path_is_refused(self):
        self.assertEqual(self.dav("MKCOL", "/alice/work/x.ics").status_code, 403)


class TestReports(ServerTest):

    def report(self, path, body, depth="1"):
        return self.dav("REPORT", path, body, depth=depth)

    def sync(self, token=""):
        return self.report("/alice/work/", (
            f'<?xml version="1.0"?><D:sync-collection {D}>'
            f"<D:sync-token>{token}</D:sync-token>"
            "<D:prop><D:getetag/></D:prop></D:sync-collection>"))

    def token_from(self, response):
        return re.search(r"<D:sync-token>([^<]*)</D:sync-token>", response.text).group(1)

    def test_initial_sync_lists_everything(self):
        response = self.sync()
        self.assertEqual(response.status_code, 207)
        self.assertIn("/alice/work/standup%40x.ics", hrefs(response))

    def test_delta_sync_reports_only_changes(self):
        token = self.token_from(self.sync())
        self.store.put_resource("alice", "work", to_resource(JULY))
        response = self.sync(token)
        self.assertIn("/alice/work/july%40x.ics", hrefs(response))
        self.assertNotIn("/alice/work/standup%40x.ics", hrefs(response))

    def test_deletion_appears_as_404_inside_the_report(self):
        token = self.token_from(self.sync())
        self.store.delete_resource("alice", "work", "standup@x.ics")
        response = self.sync(token)
        self.assertIn("404 Not Found", response.text)

    def test_expired_token_is_refused_with_the_precondition(self):
        # RFC 6578 3.2: the client must resync rather than be handed a partial
        # answer it would take for the whole truth.
        response = self.sync("no-such-token")
        self.assertEqual(response.status_code, 403)
        self.assertIn("valid-sync-token", response.text)

    def test_multiget_returns_the_requested_hrefs(self):
        body = (f'<?xml version="1.0"?><C:calendar-multiget {D} {C}>'
                "<D:prop><D:getetag/><C:calendar-data/></D:prop>"
                "<D:href>/alice/work/standup%40x.ics</D:href>"
                "</C:calendar-multiget>")
        response = self.report("/alice/work/", body)
        self.assertIn("BEGIN:VCALENDAR", response.text)

    def test_multiget_reports_a_missing_href_as_404(self):
        body = (f'<?xml version="1.0"?><C:calendar-multiget {D} {C}>'
                "<D:prop><D:getetag/></D:prop>"
                "<D:href>/alice/work/gone.ics</D:href></C:calendar-multiget>")
        self.assertIn("404 Not Found", self.report("/alice/work/", body).text)

    def query(self, start, end):
        body = (f'<?xml version="1.0"?><C:calendar-query {D} {C}>'
                "<D:prop><D:getetag/></D:prop><C:filter>"
                '<C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT">'
                f'<C:time-range start="{start}" end="{end}"/>'
                "</C:comp-filter></C:comp-filter></C:filter></C:calendar-query>")
        return self.report("/alice/work/", body)

    def test_time_range_matches_a_recurring_series_by_its_instances(self):
        # The stored DTSTART says when the series began, not whether any of it
        # falls in the window -- only expansion can answer that.
        self.store.put_resource("alice", "work", to_resource(JULY))
        self.assertIn("/alice/work/standup%40x.ics", hrefs(self.query(
            "20260316T000000Z", "20260401T000000Z")))

    def test_time_range_excludes_what_falls_outside(self):
        self.store.put_resource("alice", "work", to_resource(JULY))
        found = hrefs(self.query("20260701T000000Z", "20260801T000000Z"))
        self.assertIn("/alice/work/july%40x.ics", found)
        self.assertNotIn("/alice/work/standup%40x.ics", found)

    def test_empty_window_matches_nothing(self):
        self.assertEqual(hrefs(self.query("20200101T000000Z", "20200201T000000Z")), [])

    def test_unknown_report_is_refused(self):
        body = f'<?xml version="1.0"?><D:nonsense-report {D}/>'
        response = self.report("/alice/work/", body)
        self.assertEqual(response.status_code, 403)
        self.assertIn("supported-report", response.text)

    def test_malformed_report_body_is_400(self):
        self.assertEqual(self.report("/alice/work/", "<not xml").status_code, 400)


class TestProppatch(ServerTest):

    def test_unwritable_property_is_reported_not_silently_dropped(self):
        body = (f'<?xml version="1.0"?><D:propertyupdate {D}><D:set><D:prop>'
                "<D:getetag>nope</D:getetag></D:prop></D:set></D:propertyupdate>")
        response = self.dav("PROPPATCH", "/alice/work/", body)
        self.assertEqual(response.status_code, 207)
        self.assertIn("403 Forbidden", response.text)

    def test_proppatch_on_a_missing_collection_is_404(self):
        body = (f'<?xml version="1.0"?><D:propertyupdate {D}><D:set><D:prop>'
                "<D:displayname>x</D:displayname></D:prop></D:set></D:propertyupdate>")
        self.assertEqual(self.dav("PROPPATCH", "/alice/nope/", body).status_code, 404)


class TestBothBackends(unittest.TestCase):
    """The protocol layer only speaks to Store, so it must not care which."""

    def test_the_file_backend_serves_identically(self):
        root = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        store = open_store(root, "file")
        store.create_collection("alice", "work", CollectionType.CALENDAR, "Work")
        store.put_resource("alice", "work", to_resource(SERIES))

        client = TestClient(create_app(store, OpenAuthenticator()))
        response = client.get("/alice/work/standup@x.ics", auth=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"DTSTART;TZID={NY}:20260302T090000", response.text)


if __name__ == "__main__":
    unittest.main()
