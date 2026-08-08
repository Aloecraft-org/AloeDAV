"""
Who is asking.

HTTP Basic, because it is what every CalDAV and CardDAV client implements and
several implement *only*. That makes the password recoverable by anyone who can
read the connection, so the server must be run behind TLS; there is no way to
fix that from this side and pretending otherwise would be worse than saying it.

Passwords are stored as PBKDF2-HMAC-SHA256 with a per-user salt, verified with
a constant-time comparison. No new dependency: hashlib has had this since 3.4,
and reaching for bcrypt would add a build-time dependency to a library whose
whole install is currently pure Python plus SQLite.
"""
import base64
import hashlib
import hmac
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

USERS_FILENAME = "users.json"

# Cost. High enough to be a real obstacle, low enough that a syncing client
# hitting the server every few seconds does not spend its life here -- Basic
# sends credentials on *every* request, so this runs constantly.
ITERATIONS = 200_000
SALT_BYTES = 16


def hash_password(password: str, salt: bytes = None, iterations: int = ITERATIONS) -> dict:
    salt = salt or os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"algorithm": "pbkdf2_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": base64.b64encode(derived).decode("ascii")}


def verify_password(password: str, record: dict) -> bool:
    if not record or record.get("algorithm") != "pbkdf2_sha256":
        return False
    try:
        salt = base64.b64decode(record["salt"])
        expected = base64.b64decode(record["hash"])
        iterations = int(record["iterations"])
    except (KeyError, ValueError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


class Authenticator(ABC):

    @abstractmethod
    def check(self, user: str, password: str) -> bool:
        ...

    @property
    def realm(self) -> str:
        return "AloeDAV"


class FileAuthenticator(Authenticator):
    """
    Users in a JSON file beside the store.

    Read on every check rather than cached, so adding a user takes effect
    without a restart. The file is small and the OS caches it; the PBKDF2 round
    that follows dominates either way.
    """

    def __init__(self, path, iterations: int = ITERATIONS):
        self.path = Path(path)
        # Cost is a deployment decision, not a constant: a test suite that pays
        # production cost on every request is a test suite people stop running.
        # Verification always uses the count recorded with the hash, so lowering
        # this never invalidates existing passwords.
        self.iterations = iterations

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                return json.load(stream)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            # A corrupt user file must not authenticate everyone.
            return {}

    def _save(self, users: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(users, stream, indent=2, sort_keys=True)
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)

    def users(self) -> list[str]:
        return sorted(self._load())

    def add_user(self, user: str, password: str) -> None:
        users = self._load()
        users[user] = hash_password(password, iterations=self.iterations)
        self._save(users)

    def remove_user(self, user: str) -> bool:
        users = self._load()
        if user not in users:
            return False
        del users[user]
        self._save(users)
        return True

    def check(self, user: str, password: str) -> bool:
        record = self._load().get(user)
        if record is None:
            # Spend the same work on an unknown user as on a known one, so
            # response timing does not enumerate accounts.
            hash_password(password, iterations=self.iterations)
            return False
        return verify_password(password, record)


class OpenAuthenticator(Authenticator):
    """
    Accepts any credentials, trusting the username.

    For local single-user use and tests only. It is never the default: a
    calendar server that authenticates nobody, reachable from a network, hands
    every user's data to anyone who guesses a name.
    """

    def check(self, user: str, password: str) -> bool:
        return bool(user)


def read_basic_credentials(header: str) -> Optional[tuple[str, str]]:
    """Reads an Authorization header, or None if it is not usable Basic."""
    if not header:
        return None
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    user, separator, password = decoded.partition(":")
    if not separator:
        return None
    return user, password
