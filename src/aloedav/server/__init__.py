"""
The CalDAV and CardDAV server.

One catch-all route handles every method, because WebDAV addresses an open-ended
tree rather than a fixed set of endpoints: the path decides *what* is being
acted on and the method decides *what is done to it*, so per-path routing would
mean enumerating a namespace that only the store knows.

The store is synchronous and does blocking I/O, so every call goes through
`run_in_threadpool`. That keeps storage as plain code that knows nothing about
async, and keeps one slow read from stalling every other client's sync.

Authorization is deliberately coarse and stated here rather than scattered: a
principal may act on its own tree and no other. There is no sharing model yet,
so anything else is a 403 rather than a half-answer.
"""
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from aloedav.server import methods
from aloedav.server.auth import Authenticator, read_basic_credentials
from aloedav.server.paths import Kind, parse_path, principal_path

HANDLERS = {
    "OPTIONS": methods.handle_options,
    "PROPFIND": methods.handle_propfind,
    "PROPPATCH": methods.handle_proppatch,
    "GET": methods.handle_get,
    "HEAD": methods.handle_head,
    "PUT": methods.handle_put,
    "DELETE": methods.handle_delete,
    "MKCOL": methods.handle_mkcol,
    "MKCALENDAR": methods.handle_mkcalendar,
    "REPORT": methods.handle_report,
}

SUPPORTED_METHODS = sorted(HANDLERS) + ["POST"]

# Every response carries these: clients check the DAV header on more than just
# OPTIONS, and some refuse to proceed without it.
BASE_HEADERS = {"DAV": methods.DAV_COMPLIANCE}


class ServerRequest:
    """What a handler needs, with the body already read."""

    __slots__ = ("headers", "body", "user", "method", "path", "query_params")

    def __init__(self, request: Request, body: bytes, user: str):
        self.headers = request.headers
        self.body = body
        self.user = user
        self.method = request.method
        self.path = request.url.path
        self.query_params = request.query_params


def _unauthorized(realm: str) -> Response:
    return Response(status_code=401, headers={
        "WWW-Authenticate": f'Basic realm="{realm}", charset="UTF-8"',
        **BASE_HEADERS})


async def _well_known(request: Request) -> Response:
    """
    RFC 6764 discovery.

    A client is given the service root rather than a principal, because at this
    point nobody has authenticated and the server does not know whose principal
    to name. The client follows up with PROPFIND for current-user-principal.
    """
    return RedirectResponse("/", status_code=301, headers=BASE_HEADERS)


async def dispatch(request: Request) -> Response:
    app = request.app
    authenticator: Authenticator = app.state.authenticator
    store = app.state.store

    method = request.method.upper()
    if method not in HANDLERS:
        return Response(status_code=405, headers={
            "Allow": methods.ALLOWED_METHODS, **BASE_HEADERS})

    # OPTIONS is answered without credentials: a client sends it first to find
    # out whether this is a DAV server at all, and challenging it there makes
    # some clients abandon account setup before they ever try to authenticate.
    credentials = read_basic_credentials(request.headers.get("Authorization"))
    if method == "OPTIONS" and credentials is None:
        return _with_base(methods.handle_options(None, None, None))

    if credentials is None:
        return _unauthorized(authenticator.realm)
    user, password = credentials
    if not await run_in_threadpool(authenticator.check, user, password):
        return _unauthorized(authenticator.realm)

    target = parse_path(request.url.path)

    # One principal, one tree. No sharing model exists, so reaching into
    # another user's namespace is refused outright rather than answered
    # partially.
    if target.user is not None and target.user != user:
        return _with_base(Response(status_code=403))

    body = await request.body()
    server_request = ServerRequest(request, body, user)
    handler = HANDLERS[method]

    try:
        response = await run_in_threadpool(handler, target, server_request, store)
    except Exception:                                    # pragma: no cover
        app.logger.exception("unhandled error serving %s %s", method, request.url.path) \
            if getattr(app, "logger", None) else None
        raise
    return _with_base(response)


def _with_base(response: Response) -> Response:
    for name, value in BASE_HEADERS.items():
        response.headers[name] = value
    return response


def create_app(store, authenticator: Authenticator, debug: bool = False) -> Starlette:
    """Builds the DAV server over `store`."""
    app = Starlette(
        debug=debug,
        routes=[
            Route("/.well-known/caldav", _well_known, methods=["GET", "PROPFIND", "OPTIONS"]),
            Route("/.well-known/carddav", _well_known, methods=["GET", "PROPFIND", "OPTIONS"]),
            # One route for the whole tree. `path` matches greedily, including
            # slashes, so every depth arrives here and paths.parse_path decides
            # what it addresses.
            Route("/{path:path}", dispatch, methods=SUPPORTED_METHODS),
        ])
    app.state.store = store
    app.state.authenticator = authenticator
    return app
