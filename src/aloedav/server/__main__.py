"""
Runs the CalDAV and CardDAV server.

    python -m aloedav.server useradd alice       # create an account
    python -m aloedav.server --root ./data       # serve

Point a client at http://host:port/ and it discovers the rest. The read-only
browser view is mounted at /.web/ on the same port, so one process serves both
and there is never a second writer against the store.

Serve over TLS in anything but a trusted local network. Basic authentication
puts the password on the wire on every request, and no amount of care on this
side changes that.
"""
import argparse
import getpass
import sys

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from aloedav.server import create_app, dispatch, _well_known, SUPPORTED_METHODS
from aloedav.server.auth import USERS_FILENAME, FileAuthenticator
from aloedav.storage.backends import (BACKENDS, DEFAULT_BACKEND, DEFAULT_ROOT,
                                      detect_backend, open_store)
from aloedav.web import create_app as create_browser_app

# A DAV client never addresses this: the leading dot is refused as a user name
# by the store, so no collection can ever collide with it.
BROWSER_PREFIX = "/.web"


def build_application(store, authenticator, debug: bool = False) -> Starlette:
    """The DAV tree, with the browser view mounted beside it."""
    dav = create_app(store, authenticator, debug=debug)
    application = Starlette(debug=debug, routes=[
        # Mounted first so the DAV catch-all does not swallow it.
        Mount(BROWSER_PREFIX, app=create_browser_app(store, debug=debug)),
        Route("/.well-known/caldav", _well_known, methods=["GET", "PROPFIND", "OPTIONS"]),
        Route("/.well-known/carddav", _well_known, methods=["GET", "PROPFIND", "OPTIONS"]),
        Route("/{path:path}", dispatch, methods=SUPPORTED_METHODS),
    ])
    application.state.store = store
    application.state.authenticator = authenticator
    return application


def _authenticator(root, iterations=None) -> FileAuthenticator:
    from pathlib import Path
    path = Path(root) / USERS_FILENAME
    return (FileAuthenticator(path, iterations=iterations) if iterations
            else FileAuthenticator(path))


def run_useradd(args) -> int:
    authenticator = _authenticator(args.root)
    password = args.password or getpass.getpass(f"password for {args.user}: ")
    if not password:
        print("a password is required", file=sys.stderr)
        return 1
    authenticator.add_user(args.user, password)
    print(f"user {args.user!r} added")
    return 0


def run_userdel(args) -> int:
    if _authenticator(args.root).remove_user(args.user):
        print(f"user {args.user!r} removed")
        return 0
    print(f"no such user: {args.user}", file=sys.stderr)
    return 1


def run_userlist(args) -> int:
    users = _authenticator(args.root).users()
    print("\n".join(users) if users else "(no users yet)")
    return 0


def run_serve(args) -> int:
    backend = args.backend or detect_backend(args.root) or DEFAULT_BACKEND
    store = open_store(args.root, backend)
    authenticator = _authenticator(args.root)

    if not authenticator.users():
        # A server nobody can log into is not a running server, and the reason
        # is not obvious from a 401.
        print("no users yet -- create one first:\n"
              f"  python -m aloedav.server --root {args.root} useradd <name>",
              file=sys.stderr)
        return 1

    print(f"storage : {backend} under {args.root}")
    print(f"users   : {', '.join(authenticator.users())}")
    print(f"caldav  : http://{args.host}:{args.port}/")
    print(f"browse  : http://{args.host}:{args.port}{BROWSER_PREFIX}/")
    uvicorn.run(build_application(store, authenticator),
                host=args.host, port=args.port)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="aloedav.server", description="AloeDAV CalDAV/CardDAV server")
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help=f"storage directory (default: {DEFAULT_ROOT})")
    parser.add_argument("--backend", choices=BACKENDS, default=None,
                        help=f"storage backend (default: {DEFAULT_BACKEND}, or "
                             "whichever already holds data)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)

    subcommands = parser.add_subparsers(dest="command")
    adder = subcommands.add_parser("useradd", help="create or update an account")
    adder.add_argument("user")
    adder.add_argument("--password", default=None,
                       help="read from a prompt when omitted, which keeps it "
                            "out of the shell history")
    remover = subcommands.add_parser("userdel", help="remove an account")
    remover.add_argument("user")
    subcommands.add_parser("userlist", help="list accounts")

    args = parser.parse_args(argv)
    return {"useradd": run_useradd,
            "userdel": run_userdel,
            "userlist": run_userlist}.get(args.command, run_serve)(args)


if __name__ == "__main__":
    raise SystemExit(main())
