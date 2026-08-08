"""
XML for the server side of WebDAV.

ElementTree rather than xmltodict, which the client uses. The client only has
to read a body someone else produced, and can afford a lossy dict view of it. A
server has to *write* bodies that other people's clients will parse, which means
controlling namespace prefixes, element order and empty-element form exactly.

Property names are handled in Clark notation -- `{DAV:}displayname` -- because
that is what ElementTree produces when it parses a namespaced document, and
carrying the same spelling end to end avoids a translation layer whose only job
would be to introduce mistakes.
"""
from xml.etree import ElementTree

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
CARDDAV = "urn:ietf:params:xml:ns:carddav"
CALSERVER = "http://calendarserver.org/ns/"

# Prefixes clients recognise on sight. Registering them globally makes
# ElementTree emit `D:response` rather than `ns0:response`; the wire meaning is
# identical, but real clients have been known to choke on the generated form.
PREFIXES = {"D": DAV, "C": CALDAV, "CR": CARDDAV, "CS": CALSERVER}
for _prefix, _uri in PREFIXES.items():
    ElementTree.register_namespace(_prefix, _uri)


def qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def dav(local: str) -> str:
    return qname(DAV, local)


def caldav(local: str) -> str:
    return qname(CALDAV, local)


def carddav(local: str) -> str:
    return qname(CARDDAV, local)


def calserver(local: str) -> str:
    return qname(CALSERVER, local)


def split(name: str) -> tuple[str, str]:
    """Clark notation back into (namespace, local name)."""
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return namespace, local
    return "", name


def parse(body: bytes):
    """
    Parses a request body, or returns None when there is none.

    A malformed body raises, and callers turn that into 400. Guessing at
    half-parsed XML would mean acting on a request nobody made.
    """
    if not body or not body.strip():
        return None
    return ElementTree.fromstring(body)


def serialize(element) -> bytes:
    return (b'<?xml version="1.0" encoding="utf-8"?>\n'
            + ElementTree.tostring(element, encoding="utf-8", xml_declaration=False))


def element(tag: str, text: str = None, children=(), attrib: dict = None):
    """
    Builds one element.

    Attributes arrive as an explicit dict rather than keyword arguments: XML
    attribute names include `name`, `version` and `content-type`, which would
    collide with this function's own parameters or be unspellable as Python
    identifiers.
    """
    node = ElementTree.Element(tag, attrib or {})
    if text is not None:
        node.text = text
    for child in children:
        node.append(child)
    return node


def href(path: str):
    return element(dav("href"), path)


def status_line(code: int, reason: str) -> str:
    return f"HTTP/1.1 {code} {reason}"


OK = status_line(200, "OK")
NOT_FOUND = status_line(404, "Not Found")
FORBIDDEN = status_line(403, "Forbidden")


def propstat(properties: list, status: str):
    """One <propstat>: a group of properties sharing an outcome."""
    return element(dav("propstat"), children=[
        element(dav("prop"), children=properties),
        element(dav("status"), status)])


def response(path: str, propstats: list):
    return element(dav("response"), children=[href(path), *propstats])


def response_with_status(path: str, status: str):
    """A <response> reporting an outcome for the whole resource, not per-property."""
    return element(dav("response"), children=[href(path), element(dav("status"), status)])


def multistatus(responses: list, sync_token: str = None) -> bytes:
    children = list(responses)
    if sync_token is not None:
        children.append(element(dav("sync-token"), sync_token))
    return serialize(element(dav("multistatus"), children=children))


def error_document(condition: str, namespace: str = DAV) -> bytes:
    """
    A DAV:error naming a precondition, which is how a client is told *why* a
    request failed rather than merely that it did.
    """
    return serialize(element(dav("error"), children=[element(qname(namespace, condition))]))


def requested_properties(request_element) -> tuple[list, bool, bool]:
    """
    Reads a PROPFIND body into (names, wants_all, names_only).

    An absent body means allprop, per RFC 4918 9.1: a client that sends nothing
    is asking for everything, not for nothing.
    """
    if request_element is None:
        return [], True, False
    if request_element.find(dav("allprop")) is not None:
        return [], True, False
    if request_element.find(dav("propname")) is not None:
        return [], False, True
    prop = request_element.find(dav("prop"))
    if prop is None:
        return [], True, False
    return [child.tag for child in prop], False, False
