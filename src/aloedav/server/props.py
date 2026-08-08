"""
Answering property requests.

Each kind of URL has a set of properties it can report. A PROPFIND asks for
some of them and gets back two groups: the ones that were found, and the ones
that were not, each with its own status. Reporting an unknown property as 404
rather than omitting it is what lets a client tell "this server does not have
that" from "this server ignored my question".

The set below is what a real client needs to discover and sync a collection,
not everything RFC 4918, 4791 and 6352 define. Properties outside it are
answered 404, which is a truthful answer and one clients handle.
"""
from aloedav.collection import CollectionType, ComponentSet
from aloedav.server import xmlutil as x
from aloedav.server.paths import Kind, collection_path, principal_path

# Reports this server can run, advertised so a client knows what to try rather
# than probing and handling failures.
COLLECTION_REPORTS = ("sync-collection", "calendar-query", "calendar-multiget",
                      "addressbook-query", "addressbook-multiget")

COMPONENT_NAMES = ((ComponentSet.VEVENT, "VEVENT"),
                   (ComponentSet.VTODO, "VTODO"),
                   (ComponentSet.VJOURNAL, "VJOURNAL"))


def _resourcetype(*children):
    return x.element(x.dav("resourcetype"), children=list(children))


def _supported_report_set():
    return x.element(x.dav("supported-report-set"), children=[
        x.element(x.dav("supported-report"), children=[
            x.element(x.dav("report"), children=[x.element(x.dav(name))])])
        for name in COLLECTION_REPORTS])


def _current_user_principal(user: str):
    return x.element(x.dav("current-user-principal"),
                     children=[x.href(principal_path(user))])


def _privilege_set():
    # Everything, because a principal owns its own home set and no sharing
    # model exists yet. Clients read this to decide whether to offer editing;
    # omitting it makes some of them go read-only.
    return x.element(x.dav("current-user-privilege-set"), children=[
        x.element(x.dav("privilege"), children=[x.element(x.dav(name))])
        for name in ("read", "write", "write-properties", "write-content",
                     "bind", "unbind", "read-current-user-privilege-set")])


def root_properties(user: str) -> dict:
    return {
        x.dav("resourcetype"): lambda: _resourcetype(x.element(x.dav("collection"))),
        x.dav("current-user-principal"): lambda: _current_user_principal(user),
        x.dav("principal-collection-set"): lambda: x.element(
            x.dav("principal-collection-set"), children=[x.href("/")]),
        x.dav("displayname"): lambda: x.element(x.dav("displayname"), "AloeDAV"),
    }


def principal_properties(user: str) -> dict:
    home = principal_path(user)
    return {
        x.dav("resourcetype"): lambda: _resourcetype(
            x.element(x.dav("collection")), x.element(x.dav("principal"))),
        x.dav("displayname"): lambda: x.element(x.dav("displayname"), user),
        x.dav("current-user-principal"): lambda: _current_user_principal(user),
        x.dav("principal-URL"): lambda: x.element(
            x.dav("principal-URL"), children=[x.href(home)]),
        x.dav("principal-collection-set"): lambda: x.element(
            x.dav("principal-collection-set"), children=[x.href("/")]),
        # Both home sets point at the principal itself: calendars and address
        # books live side by side under one user.
        x.caldav("calendar-home-set"): lambda: x.element(
            x.caldav("calendar-home-set"), children=[x.href(home)]),
        x.carddav("addressbook-home-set"): lambda: x.element(
            x.carddav("addressbook-home-set"), children=[x.href(home)]),
        x.caldav("calendar-user-address-set"): lambda: x.element(
            x.caldav("calendar-user-address-set"), children=[x.href(home)]),
        x.dav("supported-report-set"): _supported_report_set,
        x.dav("current-user-privilege-set"): _privilege_set,
        x.dav("owner"): lambda: x.element(x.dav("owner"), children=[x.href(home)]),
    }


def collection_properties(info) -> dict:
    is_calendar = info.collection_type is CollectionType.CALENDAR
    path = collection_path(info.user, info.collection_id)

    def resourcetype():
        kind = (x.element(x.caldav("calendar")) if is_calendar
                else x.element(x.carddav("addressbook")))
        return _resourcetype(x.element(x.dav("collection")), kind)

    def component_set():
        return x.element(x.caldav("supported-calendar-component-set"), children=[
            x.element(x.caldav("comp"), attrib={"name": name})
            for flag, name in COMPONENT_NAMES if flag in info.component_set])

    properties = {
        x.dav("resourcetype"): resourcetype,
        x.dav("displayname"): lambda: x.element(x.dav("displayname"), info.displayname),
        x.dav("current-user-principal"): lambda: _current_user_principal(info.user),
        x.dav("owner"): lambda: x.element(
            x.dav("owner"), children=[x.href(principal_path(info.user))]),
        x.dav("supported-report-set"): _supported_report_set,
        x.dav("current-user-privilege-set"): _privilege_set,
        # getctag is the calendarserver extension every client polls to decide
        # whether a full listing is worth fetching; sync-token is the RFC 6578
        # equivalent. Both are served from the same counter.
        x.calserver("getctag"): lambda: x.element(x.calserver("getctag"), info.ctag),
        x.dav("sync-token"): lambda: x.element(x.dav("sync-token"), info.sync_token),
    }
    if is_calendar:
        properties[x.caldav("supported-calendar-component-set")] = component_set
        properties[x.caldav("calendar-description")] = lambda: x.element(
            x.caldav("calendar-description"), info.description)
        properties[x.caldav("supported-calendar-data")] = lambda: x.element(
            x.caldav("supported-calendar-data"), children=[
                x.element(x.caldav("calendar-data"),
                          attrib={"content-type": "text/calendar", "version": "2.0"})])
    else:
        properties[x.carddav("addressbook-description")] = lambda: x.element(
            x.carddav("addressbook-description"), info.description)
        properties[x.carddav("supported-address-data")] = lambda: x.element(
            x.carddav("supported-address-data"), children=[
                x.element(x.carddav("address-data"),
                          attrib={"content-type": "text/vcard", "version": "3.0"})])
    return properties


def resource_properties(resource, body: bytes) -> dict:
    return {
        x.dav("resourcetype"): lambda: _resourcetype(),
        x.dav("getetag"): lambda: x.element(x.dav("getetag"), quote_etag(resource.etag)),
        x.dav("getcontenttype"): lambda: x.element(
            x.dav("getcontenttype"), resource.content_type),
        x.dav("getcontentlength"): lambda: x.element(
            x.dav("getcontentlength"), str(len(body))),
        x.dav("current-user-principal"): lambda: _current_user_principal(
            getattr(resource, "_user", "") or ""),
        x.caldav("calendar-data"): lambda: x.element(
            x.caldav("calendar-data"), body.decode("utf-8")),
        x.carddav("address-data"): lambda: x.element(
            x.carddav("address-data"), body.decode("utf-8")),
    }


def quote_etag(etag: str) -> str:
    """
    ETags go on the wire quoted (RFC 9110 8.8.3).

    Clients compare the quoted form verbatim, so a server that omits the quotes
    gets its conditional requests silently ignored by some of them.
    """
    if not etag:
        return ""
    return etag if etag.startswith(('"', "W/")) else f'"{etag}"'


def unquote_etag(etag: str) -> str:
    return (etag or "").strip().removeprefix("W/").strip('"')


def resolve(available: dict, names: list, wants_all: bool, names_only: bool):
    """
    Splits a property request into what could be answered and what could not.

    `allprop` deliberately omits the expensive ones -- notably calendar-data,
    which would inline every resource's whole body into a listing. RFC 4918 9.1
    allows this, and a client that wants the data asks for it by name.
    """
    found, missing = [], []

    if names_only:
        return [x.element(name) for name in available], []

    if wants_all:
        for name, build in available.items():
            if name in (x.caldav("calendar-data"), x.carddav("address-data")):
                continue
            found.append(build())
        return found, missing

    for name in names:
        build = available.get(name)
        if build is None:
            missing.append(x.element(name))
        else:
            found.append(build())
    return found, missing


def propstats(found: list, missing: list) -> list:
    result = []
    if found:
        result.append(x.propstat(found, x.OK))
    if missing:
        result.append(x.propstat(missing, x.NOT_FOUND))
    if not result:
        result.append(x.propstat([], x.OK))
    return result
