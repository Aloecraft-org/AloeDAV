"""
Resources: the unit the protocol actually moves.

A component (VEVENT, VTODO, VCARD ...) is not what GET and PUT operate on. The
wire unit is the *resource* -- one file at one href, carrying one ETag. For
CardDAV that is a single VCARD, so the distinction is invisible. For CalDAV it
is a VCALENDAR that may hold several components:

  * a recurring master plus one VEVENT per modified instance, all sharing a UID
    and distinguished by RECURRENCE-ID (RFC 5545 3.8.4.4), and
  * the VTIMEZONE definitions those components' TZID parameters refer to.

Treating a component as the unit loses that grouping: two components sharing a
UID collide on filename, and writing either one back drops its siblings, which
destroys a recurring series the moment anything edits one instance of it.
"""
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from aloedav.model import ModelUtil
from aloedav.model.m01_base import CalendarItem, Item
from aloedav.model.m02_vcard import VCARD


class Resource(BaseModel, ABC):
    """One addressable WebDAV resource."""

    etag: Optional[str] = None
    raw_contents: Optional[str] = None

    @property
    @abstractmethod
    def content_type(self) -> str:
        """Value for the Content-Type header on PUT."""

    @abstractmethod
    def filename(self) -> str:
        """Last path segment identifying this resource within its collection."""

    @abstractmethod
    def to_webdav_string(self) -> str:
        """The resource's body, exactly as it goes on the wire."""

    @abstractmethod
    def items(self) -> list[Item]:
        """Every modelled component in this resource."""


class VCardResource(Resource):
    """A CardDAV resource: exactly one VCARD."""

    card: VCARD

    @property
    def content_type(self) -> str:
        return self.card.content_type

    @property
    def uid(self) -> Optional[str]:
        return self.card.uid

    def filename(self) -> str:
        return self.card.filename()

    def to_webdav_string(self) -> str:
        return self.card.to_vcard_string()

    def items(self) -> list[Item]:
        return [self.card]


class VCalendarResource(Resource):
    """
    A CalDAV resource: one VCALENDAR wrapping one or more components.

    RFC 4791 4.1 requires a conformant calendar object resource to hold a single
    UID and a single component type, but plain .ics files routinely break both
    rules, so `components` is an unrestricted list and `uid` reports the first.
    """

    version: str = "2.0"
    prod_id: Optional[str] = "-//aloecraft.org//AloeDAV 1.0//EN"
    components: list[CalendarItem] = Field(default_factory=list)

    # VCALENDAR-level content the model does not represent: CALSCALE, METHOD,
    # and the VTIMEZONE blocks that TZID parameters point at.
    calendar_properties: list[str] = Field(default_factory=list)
    calendar_components: list[str] = Field(default_factory=list)

    file_ext: str = "ics"

    @property
    def content_type(self) -> str:
        return "text/calendar; charset=utf-8"

    @property
    def uid(self) -> Optional[str]:
        return self.components[0].uid if self.components else None

    @property
    def master(self) -> Optional[CalendarItem]:
        """The series master -- the component with no RECURRENCE-ID."""
        return next((c for c in self.components if c.recurrence_id is None), None)

    @property
    def overrides(self) -> list[CalendarItem]:
        """Components that replace a single instance of the series."""
        return [c for c in self.components if c.recurrence_id is not None]

    def override_for(self, recurrence_id) -> Optional[CalendarItem]:
        return next((c for c in self.overrides if c.recurrence_id == recurrence_id), None)

    def filename(self) -> str:
        if not self.components:
            raise ValueError("cannot name an empty resource")
        # One name per resource, taken from the shared UID, so a master and its
        # overrides address the same file instead of overwriting each other.
        return f"{self.uid}.{self.file_ext}"

    def to_webdav_string(self) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            f"VERSION:{self.version}",
            f"PRODID:{ModelUtil.escape_text(self.prod_id)}",
            *self.calendar_properties,
            *self.calendar_components,
        ]
        # Master first, then overrides, so the ordering is stable across writes
        # regardless of the order the server happened to send them in.
        for component in sorted(self.components,
                                key=lambda c: (c.recurrence_id is not None,
                                               str(c.recurrence_id or ""))):
            lines.append(component.to_component_string())
        lines.append("END:VCALENDAR")
        return ModelUtil.join_lines(lines)

    def items(self) -> list[Item]:
        return list(self.components)
