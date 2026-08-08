"""
A read-only browser view over a Store.

Notes for a Flask reader, since the shapes differ more than the ideas do:

  * Routes are a list of `Route(path, handler)` passed to the app, rather than
    `@app.route` decorators. A DAV server needs this later anyway -- `Route`
    takes `methods=["PROPFIND", "REPORT", ...]`, which Flask's decorator does
    not do gracefully.
  * A handler is `async def handler(request)` and receives the request
    explicitly, instead of a plain function reading a thread-local `request`.
  * Path segments arrive in `request.path_params`, query string in
    `request.query_params`, and you return a Response object rather than a
    string.
  * `run_in_threadpool` is the one genuinely new obligation: the store does
    blocking file I/O, and calling it directly on the event loop would stall
    every other request. Wrapping it keeps the async layer honest without the
    store having to know anything about async.

This view never writes. It is a window onto what the store holds, and the DAV
server will be a second front end over the same interface.
"""
from datetime import date, datetime, timedelta, timezone

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.routing import Route

from aloedav.collection import CollectionType
from aloedav.model.m03_occurrence import expand
from aloedav.storage import CollectionNotFound, ResourceNotFoundInStore, StorageError
from aloedav.web import render

# How much of the calendar one page shows.
WINDOW_DAYS = 30


def _requested_start(request) -> datetime:
    """The window start, from ?start=YYYY-MM-DD, defaulting to today."""
    raw = request.query_params.get("start", "")
    try:
        anchor = date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        anchor = date.today()
    return datetime(anchor.year, anchor.month, anchor.day, tzinfo=timezone.utc)


async def index(request):
    store = request.app.state.store
    users = await run_in_threadpool(store.users)
    return HTMLResponse(render.page("AloeDAV", render.user_list(users)))


async def user_page(request):
    store = request.app.state.store
    user = request.path_params["user"]
    collections = await run_in_threadpool(store.list_collections, user)
    return HTMLResponse(render.page(
        user, render.collection_list(user, collections),
        crumbs=[("AloeDAV", "/"), (user, None)]))


async def collection_page(request):
    store = request.app.state.store
    user = request.path_params["user"]
    collection_id = request.path_params["collection_id"]

    info = await run_in_threadpool(store.get_collection, user, collection_id)
    resources = await run_in_threadpool(store.list_resources, user, collection_id)
    crumbs = [("AloeDAV", "/"), (user, f"/{user}/"),
              (info.displayname or collection_id, None)]

    if info.collection_type is CollectionType.ADDRESSBOOK:
        body = render.card_list(user, collection_id, resources)
    else:
        window_start = _requested_start(request)
        window_end = window_start + timedelta(days=WINDOW_DAYS)
        occurrences = []
        for resource in resources:
            occurrences.extend(expand(resource, start=window_start, end=window_end))
        occurrences.sort(key=lambda o: o.starts_utc())
        body = render.agenda(
            user, collection_id, occurrences, window_start, window_end,
            previous=(window_start - timedelta(days=WINDOW_DAYS)).date().isoformat(),
            following=window_end.date().isoformat())

    return HTMLResponse(render.page(info.displayname or collection_id, body, crumbs))


async def resource_page(request):
    store = request.app.state.store
    user = request.path_params["user"]
    collection_id = request.path_params["collection_id"]
    filename = request.path_params["filename"]

    info = await run_in_threadpool(store.get_collection, user, collection_id)
    resource = await run_in_threadpool(store.get_resource, user, collection_id, filename)

    # Raw bytes on request, so the stored file can be compared against what a
    # client thinks it wrote without leaving the browser.
    if request.query_params.get("raw") is not None:
        return PlainTextResponse(resource.raw_contents or resource.to_webdav_string(),
                                 media_type=resource.content_type)

    occurrences = expand(resource, start=datetime.now(timezone.utc), limit=25)
    return HTMLResponse(render.page(
        filename, render.resource_detail(resource, occurrences),
        crumbs=[("AloeDAV", "/"), (user, f"/{user}/"),
                (info.displayname or collection_id, f"/{user}/{collection_id}/"),
                (filename, None)]))


async def _not_found(request, exc):
    return HTMLResponse(render.page("Not found", f'<p class="empty">{render.esc(exc)}</p>'),
                        status_code=404)


async def _storage_error(request, exc):
    return HTMLResponse(render.page("Storage error", f'<p class="empty">{render.esc(exc)}</p>'),
                        status_code=500)


def create_app(store, debug: bool = False) -> Starlette:
    """Builds the browser view over `store`."""
    app = Starlette(
        debug=debug,
        routes=[
            Route("/", index),
            Route("/{user}/", user_page),
            Route("/{user}/{collection_id}/", collection_page),
            Route("/{user}/{collection_id}/{filename}", resource_page),
        ],
        exception_handlers={
            CollectionNotFound: _not_found,
            ResourceNotFoundInStore: _not_found,
            StorageError: _storage_error,
        })
    app.state.store = store
    return app
