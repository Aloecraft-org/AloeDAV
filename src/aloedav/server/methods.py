"""
The WebDAV, CalDAV and CardDAV methods.

Each handler takes a parsed target and the request, and returns a Response.
They share one rule about failure: a request that cannot be satisfied gets the
status that says why -- 404 for a missing resource, 412 for a failed
precondition, 403 with a DAV:error naming the condition where the RFC defines
one. A server that answers 200 with an empty body when it did not understand
the request leaves the client believing something happened.

Nothing here reaches past the `Store` interface, so both backends serve
identically.
"""
from datetime import datetime, timezone
from xml.etree.ElementTree import ParseError as XmlParseError

from starlette.responses import Response

from aloedav.collection import CollectionType, ComponentSet
from aloedav.model.m00_datetime import DateTimeValue
from aloedav.model.m03_occurrence import expand
from aloedav.model.serial_util import to_resource
from aloedav.server import props
from aloedav.server import xmlutil as x
from aloedav.server.paths import (Kind, collection_path, principal_path,
                                  resource_path, root_path)
from aloedav.storage import (AlreadyExists, CollectionNotFound, EtagMismatch,
                             ResourceNotFoundInStore, StorageError,
                             SyncTokenExpired)

MULTISTATUS = "application/xml; charset=utf-8"

# Advertised on OPTIONS. "1, 2, 3" are the WebDAV classes; the two extension
# tokens are how a client discovers this is a calendar and contact server at
# all, and clients that do not see them will not offer to add an account.
DAV_COMPLIANCE = "1, 2, 3, calendar-access, addressbook, extended-mkcol"

ALLOWED_METHODS = ("OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, PROPPATCH, "
                   "REPORT, MKCOL, MKCALENDAR")


def multistatus_response(responses, sync_token=None) -> Response:
    return Response(x.multistatus(responses, sync_token),
                    status_code=207, media_type=MULTISTATUS)


def error_response(status: int, condition: str = None, namespace: str = x.DAV) -> Response:
    if condition is None:
        return Response(status_code=status)
    return Response(x.error_document(condition, namespace),
                    status_code=status, media_type=MULTISTATUS)


# ---- OPTIONS ----------------------------------------------------------

def handle_options(target, request, store) -> Response:
    return Response(status_code=200, headers={
        "DAV": DAV_COMPLIANCE,
        "Allow": ALLOWED_METHODS,
        "Content-Length": "0"})


# ---- PROPFIND ---------------------------------------------------------

def _depth(request) -> str:
    value = (request.headers.get("Depth") or "0").strip().lower()
    return value if value in ("0", "1", "infinity") else "0"


def _collection_response(info, names, wants_all, names_only):
    found, missing = props.resolve(props.collection_properties(info),
                                   names, wants_all, names_only)
    return x.response(collection_path(info.user, info.collection_id),
                      props.propstats(found, missing))


def _resource_response(user, collection_id, resource, names, wants_all, names_only):
    body = resource.to_webdav_string().encode("utf-8")
    available = props.resource_properties(resource, body)
    found, missing = props.resolve(available, names, wants_all, names_only)
    return x.response(resource_path(user, collection_id, resource.stored_name),
                      props.propstats(found, missing))


def handle_propfind(target, request, store) -> Response:
    try:
        document = x.parse(request.body)
    except XmlParseError:
        return Response(b"malformed PROPFIND body", status_code=400)

    names, wants_all, names_only = x.requested_properties(document)
    depth = _depth(request)
    user = target.user or request.user

    if target.kind is Kind.ROOT:
        found, missing = props.resolve(props.root_properties(request.user),
                                       names, wants_all, names_only)
        responses = [x.response(root_path(), props.propstats(found, missing))]
        if depth != "0":
            responses.append(x.response(
                principal_path(request.user),
                props.propstats(*props.resolve(
                    props.principal_properties(request.user),
                    names, wants_all, names_only))))
        return multistatus_response(responses)

    if target.kind is Kind.PRINCIPAL:
        found, missing = props.resolve(props.principal_properties(user),
                                       names, wants_all, names_only)
        responses = [x.response(principal_path(user), props.propstats(found, missing))]
        if depth != "0":
            for info in store.list_collections(user):
                responses.append(_collection_response(info, names, wants_all, names_only))
        return multistatus_response(responses)

    if target.kind is Kind.COLLECTION:
        try:
            info = store.get_collection(user, target.collection)
        except CollectionNotFound:
            return Response(status_code=404)
        responses = [_collection_response(info, names, wants_all, names_only)]
        if depth != "0":
            for resource in store.list_resources(user, target.collection):
                responses.append(_resource_response(
                    user, target.collection, resource, names, wants_all, names_only))
        return multistatus_response(responses)

    try:
        resource = store.get_resource(user, target.collection, target.resource)
    except (CollectionNotFound, ResourceNotFoundInStore):
        return Response(status_code=404)
    except StorageError:
        return Response(status_code=404)
    return multistatus_response([_resource_response(
        user, target.collection, resource, names, wants_all, names_only)])


# ---- PROPPATCH --------------------------------------------------------

# Properties a client may set. Anything else is accepted into the response as
# 403 rather than silently discarded, so the client knows it did not take.
WRITABLE = {x.dav("displayname"), x.caldav("calendar-description"),
            x.carddav("addressbook-description")}


def handle_proppatch(target, request, store) -> Response:
    if target.kind is not Kind.COLLECTION:
        return Response(status_code=403)
    try:
        document = x.parse(request.body)
    except XmlParseError:
        return Response(b"malformed PROPPATCH body", status_code=400)
    if document is None:
        return Response(status_code=400)

    try:
        store.get_collection(target.user, target.collection)
    except CollectionNotFound:
        return Response(status_code=404)

    accepted, refused = [], []
    for operation in document:
        _, local = x.split(operation.tag)
        if local not in ("set", "remove"):
            continue
        prop = operation.find(x.dav("prop"))
        for child in (prop if prop is not None else []):
            (accepted if child.tag in WRITABLE else refused).append(
                x.element(child.tag))

    # Values are not persisted yet: collection metadata is written at creation
    # and there is no update path through the Store interface. Reporting 200
    # for something not stored would be a lie, so these are reported as
    # forbidden until that path exists.
    statuses = []
    if accepted:
        statuses.append(x.propstat(accepted, x.FORBIDDEN))
    if refused:
        statuses.append(x.propstat(refused, x.FORBIDDEN))
    return multistatus_response([x.response(
        collection_path(target.user, target.collection),
        statuses or [x.propstat([], x.OK)])])


# ---- GET / HEAD -------------------------------------------------------

def handle_get(target, request, store, include_body: bool = True) -> Response:
    if target.kind is not Kind.RESOURCE:
        return Response(status_code=405, headers={"Allow": ALLOWED_METHODS})
    try:
        resource = store.get_resource(target.user, target.collection, target.resource)
    except (CollectionNotFound, ResourceNotFoundInStore, StorageError):
        return Response(status_code=404)

    body = resource.to_webdav_string().encode("utf-8")
    headers = {"ETag": props.quote_etag(resource.etag),
               "Content-Type": resource.content_type,
               "Content-Length": str(len(body))}

    # A client that already holds this version gets told so rather than sent
    # the bytes again.
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and props.unquote_etag(if_none_match) == resource.etag:
        return Response(status_code=304, headers=headers)

    return Response(body if include_body else b"", status_code=200, headers=headers)


def handle_head(target, request, store) -> Response:
    return handle_get(target, request, store, include_body=False)


# ---- PUT --------------------------------------------------------------

def handle_put(target, request, store) -> Response:
    if target.kind is not Kind.RESOURCE:
        return Response(status_code=405, headers={"Allow": ALLOWED_METHODS})

    try:
        store.get_collection(target.user, target.collection)
    except CollectionNotFound:
        return Response(status_code=409)          # no parent to put it in

    try:
        resource = to_resource(request.body.decode("utf-8"))
    except (UnicodeDecodeError, Exception):
        # RFC 4791 5.3.2: the body has to be a valid calendar object. Storing
        # something unparseable would hand the next reader a resource nobody
        # can use.
        return error_response(400, "valid-calendar-data", x.CALDAV)

    if_match = request.headers.get("If-Match")
    if_none_match = request.headers.get("If-None-Match")

    try:
        etag = store.put_resource(
            target.user, target.collection, resource,
            filename=target.resource,
            if_match=props.unquote_etag(if_match) if if_match and if_match != "*" else None,
            if_none_match=(if_none_match or "").strip() == "*")
    except AlreadyExists:
        return Response(status_code=412)
    except (EtagMismatch, ResourceNotFoundInStore):
        return Response(status_code=412)
    except StorageError as error:
        return Response(str(error).encode("utf-8"), status_code=403)

    created = if_none_match is not None or not if_match
    return Response(status_code=201 if created else 204,
                    headers={"ETag": props.quote_etag(etag)})


# ---- DELETE -----------------------------------------------------------

def handle_delete(target, request, store) -> Response:
    if_match = request.headers.get("If-Match")
    etag = props.unquote_etag(if_match) if if_match and if_match != "*" else None

    if target.kind is Kind.COLLECTION:
        try:
            store.delete_collection(target.user, target.collection)
        except CollectionNotFound:
            return Response(status_code=404)
        return Response(status_code=204)

    if target.kind is not Kind.RESOURCE:
        return Response(status_code=405, headers={"Allow": ALLOWED_METHODS})

    try:
        store.delete_resource(target.user, target.collection, target.resource,
                              if_match=etag)
    except (CollectionNotFound, ResourceNotFoundInStore):
        return Response(status_code=404)
    except EtagMismatch:
        return Response(status_code=412)
    except StorageError:
        return Response(status_code=403)
    return Response(status_code=204)


# ---- MKCOL / MKCALENDAR -----------------------------------------------

def _requested_collection_metadata(document):
    """Reads displayname, description and component set out of a MKCOL body."""
    displayname, description, components = "", "", None
    if document is None:
        return displayname, description, components

    for prop in document.iter(x.dav("prop")):
        for child in prop:
            if child.tag == x.dav("displayname"):
                displayname = child.text or ""
            elif child.tag in (x.caldav("calendar-description"),
                               x.carddav("addressbook-description")):
                description = child.text or ""
            elif child.tag == x.caldav("supported-calendar-component-set"):
                components = ComponentSet.INVALID
                for comp in child:
                    name = (comp.get("name") or "").upper()
                    if name == "VEVENT":
                        components |= ComponentSet.VEVENT
                    elif name == "VTODO":
                        components |= ComponentSet.VTODO
                    elif name == "VJOURNAL":
                        components |= ComponentSet.VJOURNAL
    return displayname, description, components


def _collection_type_of(document, default: CollectionType) -> CollectionType:
    if document is None:
        return default
    for resourcetype in document.iter(x.dav("resourcetype")):
        for child in resourcetype:
            if child.tag == x.carddav("addressbook"):
                return CollectionType.ADDRESSBOOK
            if child.tag == x.caldav("calendar"):
                return CollectionType.CALENDAR
    return default


def _make_collection(target, request, store, default_type) -> Response:
    if target.kind is not Kind.COLLECTION:
        return Response(status_code=403)
    try:
        document = x.parse(request.body)
    except XmlParseError:
        return Response(b"malformed request body", status_code=400)

    displayname, description, components = _requested_collection_metadata(document)
    collection_type = _collection_type_of(document, default_type)

    try:
        store.create_collection(target.user, target.collection, collection_type,
                                displayname or target.collection, description,
                                components if components else None)
    except AlreadyExists:
        # RFC 4918 9.3.1: the target must not already exist.
        return error_response(405, "resource-must-be-null")
    except StorageError as error:
        return Response(str(error).encode("utf-8"), status_code=403)
    return Response(status_code=201)


def handle_mkcol(target, request, store) -> Response:
    return _make_collection(target, request, store, CollectionType.CALENDAR)


def handle_mkcalendar(target, request, store) -> Response:
    return _make_collection(target, request, store, CollectionType.CALENDAR)


# ---- REPORT -----------------------------------------------------------

def handle_report(target, request, store) -> Response:
    try:
        document = x.parse(request.body)
    except XmlParseError:
        return Response(b"malformed REPORT body", status_code=400)
    if document is None:
        return Response(status_code=400)

    _, report = x.split(document.tag)
    if report == "sync-collection":
        return _sync_collection(target, document, store)
    if report in ("calendar-multiget", "addressbook-multiget"):
        return _multiget(target, document, store)
    if report in ("calendar-query", "addressbook-query"):
        return _query(target, document, store)
    return error_response(403, "supported-report")


def _requested(document):
    return x.requested_properties(document)


def _sync_collection(target, document, store) -> Response:
    if target.kind is not Kind.COLLECTION:
        return Response(status_code=403)
    token_element = document.find(x.dav("sync-token"))
    token = (token_element.text or "").strip() if token_element is not None else ""
    # An empty <sync-token/> is how a client asks for a full listing.
    token = token.rsplit("/", 1)[-1] if token else ""

    names, wants_all, names_only = _requested(document)
    try:
        result = store.sync(target.user, target.collection, token or None)
    except CollectionNotFound:
        return Response(status_code=404)
    except SyncTokenExpired:
        # RFC 6578 3.2: the client must resync rather than be handed a partial
        # answer it would mistake for the whole truth.
        return error_response(403, "valid-sync-token")

    responses = []
    for change in result.changes:
        path = resource_path(target.user, target.collection, change.filename)
        if change.deleted:
            responses.append(x.response_with_status(path, x.status_line(404, "Not Found")))
            continue
        try:
            resource = store.get_resource(target.user, target.collection, change.filename)
        except (ResourceNotFoundInStore, StorageError):
            responses.append(x.response_with_status(path, x.status_line(404, "Not Found")))
            continue
        responses.append(_resource_response(target.user, target.collection, resource,
                                            names, wants_all, names_only))
    return multistatus_response(responses, sync_token=result.sync_token)


def _multiget(target, document, store) -> Response:
    if target.kind is not Kind.COLLECTION:
        return Response(status_code=403)
    names, wants_all, names_only = _requested(document)

    responses = []
    for href in document.findall(x.dav("href")):
        path = (href.text or "").strip()
        filename = path.rstrip("/").rsplit("/", 1)[-1]
        from urllib.parse import unquote
        filename = unquote(filename)
        try:
            resource = store.get_resource(target.user, target.collection, filename)
        except (CollectionNotFound, ResourceNotFoundInStore, StorageError):
            responses.append(x.response_with_status(path, x.status_line(404, "Not Found")))
            continue
        responses.append(_resource_response(target.user, target.collection, resource,
                                            names, wants_all, names_only))
    return multistatus_response(responses)


def _time_range(document):
    """The window from a calendar-query filter, if it carries one."""
    for element in document.iter(x.caldav("time-range")):
        return (_parse_bound(element.get("start")), _parse_bound(element.get("end")))
    return None, None


def _parse_bound(value):
    parsed = DateTimeValue.parse(value) if value else None
    if parsed is None:
        return None
    return parsed.to_utc() or parsed.value.replace(tzinfo=timezone.utc)


def _requested_component_names(document) -> set:
    names = set()
    for element in document.iter(x.caldav("comp-filter")):
        name = (element.get("name") or "").upper()
        if name and name != "VCALENDAR":
            names.add(name)
    return names


def _query(target, document, store) -> Response:
    if target.kind is not Kind.COLLECTION:
        return Response(status_code=403)
    names, wants_all, names_only = _requested(document)

    try:
        resources = store.list_resources(target.user, target.collection)
    except CollectionNotFound:
        return Response(status_code=404)

    start, end = _time_range(document)
    wanted = _requested_component_names(document)

    responses = []
    for resource in resources:
        if not _matches(resource, wanted, start, end):
            continue
        responses.append(_resource_response(target.user, target.collection, resource,
                                            names, wants_all, names_only))
    return multistatus_response(responses)


def _matches(resource, wanted_components: set, start, end) -> bool:
    """
    Whether a resource satisfies a query's filters.

    A time-range is evaluated against expanded instances, which is the only way
    to answer it correctly for a recurring event: the stored DTSTART says when
    the series began, not whether any of it falls in the window.
    """
    components = getattr(resource, "components", None)
    if components is None:                       # an address book resource
        return not wanted_components

    if wanted_components:
        present = {type(component).__name__ for component in components}
        if not (present & wanted_components):
            return False

    if start is None and end is None:
        return True
    return bool(expand(resource, start=start, end=end, limit=1))
