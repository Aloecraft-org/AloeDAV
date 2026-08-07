import unittest
from datetime import datetime, timezone, timedelta

from aloedav.model import ModelUtil
from aloedav.model.serial_util import to_model, webdav_data, parse_dt
from aloedav.model.m01_base import Address, Phone, Alarm, Attendee
from aloedav.model.m02_vcard import VCARD
from aloedav.model.m02_vevent import VEVENT
from aloedav.model.m02_vtodo import VTODO
from aloedav.model.m02_vjournal import VJOURNAL
from aloedav import testdata


def reparse(item):
    """Serializes an item to its wire format and parses it back into a model."""
    return to_model(item.to_webdav_string())[0]


class TestWireFormat(unittest.TestCase):
    """
    The serialized form has to be something a server will actually accept:
    CRLF throughout, no stray blank lines, and no line over the octet limit.
    """

    def all_items(self):
        return [
            VCARD(uid="c1", fn="Forrest Gump"),
            VEVENT(uid="e1", summary="Standup", dtstart=datetime(2026, 3, 1, 9, 0)),
            VTODO(uid="t1", summary="Ship it", due=datetime(2026, 3, 2, 17, 0)),
            VJOURNAL(uid="j1", summary="Notes", dtstart=datetime(2026, 3, 1, 9, 0)),
        ]

    def test_no_leading_or_trailing_blank_lines(self):
        for item in self.all_items():
            data = item.to_webdav_string()
            self.assertFalse(data.startswith(("\r", "\n")),
                             f"{type(item).__name__} starts with a blank line")
            self.assertTrue(data.startswith("BEGIN:"),
                            f"{type(item).__name__} does not start with BEGIN")
            self.assertTrue(data.rstrip().endswith("END:VCARD")
                            or data.rstrip().endswith("END:VCALENDAR"))

    def test_line_endings_are_crlf_throughout(self):
        for item in self.all_items():
            data = item.to_webdav_string()
            # Every LF must be preceded by a CR, and no bare CR may appear.
            self.assertEqual(data.count("\n"), data.count("\r\n"),
                             f"{type(item).__name__} contains a bare LF")
            self.assertEqual(data.count("\r"), data.count("\r\n"),
                             f"{type(item).__name__} contains a bare CR")

    def test_no_empty_content_lines(self):
        for item in self.all_items():
            for line in item.to_webdav_string().split("\r\n"):
                self.assertNotEqual(line.strip(), "",
                                    f"{type(item).__name__} emits an empty content line")

    def test_lines_are_folded_at_the_octet_limit(self):
        long_text = "word " * 60
        items = [
            VCARD(uid="c1", fn="Folded", notes=long_text),
            VEVENT(uid="e1", summary="Folded", dtstart=datetime(2026, 3, 1, 9, 0),
                   description=long_text),
        ]
        for item in items:
            for line in item.to_webdav_string().split("\r\n"):
                self.assertLessEqual(len(line.encode("utf-8")), ModelUtil.FOLD_LIMIT,
                                     f"{type(item).__name__} emitted an unfolded line")

    def test_folding_survives_multibyte_characters(self):
        # Folding is defined on octets, but must not split a UTF-8 sequence.
        card = VCARD(uid="c1", fn="Unicode", notes="éèê" * 60)
        data = card.to_webdav_string()
        self.assertEqual(reparse(card).notes, card.notes)
        for line in data.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), ModelUtil.FOLD_LIMIT)


class TestTextEscaping(unittest.TestCase):
    """
    Values carrying the delimiters of the format itself have to survive a
    round trip, or a comma in a summary silently truncates the record.
    """

    HOSTILE = [
        "comma, separated",
        "semicolon; separated",
        "backslash \\ inside",
        "newline\nsecond line",
        "everything: a, b; c \\ d\ne",
    ]

    def test_summary_and_description_round_trip(self):
        for value in self.HOSTILE:
            event = VEVENT(uid="e1", summary=value, description=value,
                           location=value, dtstart=datetime(2026, 3, 1, 9, 0))
            back = reparse(event)
            self.assertEqual(back.summary, value, f"summary lost: {value!r}")
            self.assertEqual(back.description, value, f"description lost: {value!r}")
            self.assertEqual(back.location, value, f"location lost: {value!r}")

    def test_vcard_text_fields_round_trip(self):
        for value in self.HOSTILE:
            card = VCARD(uid="c1", fn=value, notes=value, organization=value)
            back = reparse(card)
            self.assertEqual(back.full_name, value, f"fn lost: {value!r}")
            self.assertEqual(back.notes, value, f"notes lost: {value!r}")
            self.assertEqual(back.organization, value, f"org lost: {value!r}")

    def test_categories_with_commas_do_not_split(self):
        card = VCARD(uid="c1", fn="Cats", categories=["a,b", "plain", "c;d"])
        self.assertEqual(reparse(card).categories, ["a,b", "plain", "c;d"])

    def test_escaped_value_does_not_create_a_new_line(self):
        event = VEVENT(uid="e1", summary="x", dtstart=datetime(2026, 3, 1, 9, 0),
                       description="line one\nUID:injected@example.com")
        lines = event.to_webdav_string().split("\r\n")
        self.assertEqual([l for l in lines if l.startswith("UID:")], ["UID:e1"])

    def test_parameter_value_with_delimiters_round_trips(self):
        event = VEVENT(uid="e1", summary="x", dtstart=datetime(2026, 3, 1, 9, 0),
                       attendees=[Attendee(email="a@example.com", name="Doe; Jane, Dr")])
        self.assertEqual(reparse(event).attendees[0].name, "Doe; Jane, Dr")

    def test_escape_unescape_are_inverse(self):
        for value in self.HOSTILE:
            self.assertEqual(ModelUtil.unescape_text(ModelUtil.escape_text(value)), value)


class TestDateTimeHandling(unittest.TestCase):

    def test_utc_datetime_keeps_its_designator(self):
        event = VEVENT(uid="e1", summary="Call",
                       dtstart=datetime(2026, 3, 1, 17, 0, tzinfo=timezone.utc))
        self.assertIn("DTSTART:20260301T170000Z", event.to_webdav_string())
        self.assertEqual(reparse(event).dtstart,
                         datetime(2026, 3, 1, 17, 0, tzinfo=timezone.utc))

    def test_offset_datetime_is_converted_to_utc(self):
        event = VEVENT(uid="e1", summary="Call",
                       dtstart=datetime(2026, 3, 1, 12, 0,
                                        tzinfo=timezone(timedelta(hours=-5))))
        self.assertIn("DTSTART:20260301T170000Z", event.to_webdav_string())

    def test_naive_datetime_stays_floating(self):
        event = VEVENT(uid="e1", summary="Call", dtstart=datetime(2026, 3, 1, 12, 0))
        self.assertIn("DTSTART:20260301T120000\r\n", event.to_webdav_string())
        self.assertIsNone(reparse(event).dtstart.tzinfo)

    def test_date_only_value_is_not_replaced_by_now(self):
        # A DATE value must parse to that date's midnight, never to "now".
        self.assertEqual(parse_dt("20260301"), datetime(2026, 3, 1, 0, 0))

    def test_unparseable_value_returns_none(self):
        for value in ("garbage", "", None, "2026-03-01"):
            self.assertIsNone(parse_dt(value), f"expected None for {value!r}")


class TestModelRoundTrip(unittest.TestCase):

    def test_vcard_full_address_survives(self):
        card = VCARD(uid="c1", fn="Forrest Gump", given_name="Forrest",
                     family_name="Gump",
                     addresses=[Address(street="100 Waters Edge", city="Baytown",
                                        state="LA", postal_code="30314",
                                        country="United States of America")])
        addr = reparse(card).addresses[0]
        self.assertEqual(addr.street, "100 Waters Edge")
        self.assertEqual(addr.city, "Baytown")
        self.assertEqual(addr.state, "LA")
        self.assertEqual(addr.postal_code, "30314")
        self.assertEqual(addr.country, "United States of America")

    def test_phone_type_and_preference_survive_together(self):
        # vCard 3.0 emits these as repeated TYPE parameters, so neither may
        # overwrite the other on the way back in.
        from aloedav.model.m00_constant import PhoneType
        card = VCARD(uid="c1", fn="Phones",
                     phones=[Phone(number="+1 555 0100", type=PhoneType.CELL,
                                   is_preferred=True)])
        phone = reparse(card).phones[0]
        self.assertEqual(phone.number, "+1 555 0100")
        self.assertEqual(phone.type, PhoneType.CELL)
        self.assertTrue(phone.is_preferred)

    def test_address_type_survives(self):
        from aloedav.model.m00_constant import AddressType
        card = VCARD(uid="c1", fn="Addr",
                     addresses=[Address(street="1 Main St", city="Town",
                                        type=AddressType.WORK)])
        self.assertEqual(reparse(card).addresses[0].type, AddressType.WORK)

    def test_vcard_identity_fields_survive(self):
        card = VCARD(uid="c1", fn="Forrest Gump", given_name="Forrest",
                     family_name="Gump", organization="Bubba Gump Shrimp Co.",
                     job_title="Shrimp Boat Captain",
                     emails=["forrestgump@example.com"],
                     phones=[Phone(number="(111) 555-1212")])
        back = reparse(card)
        self.assertEqual(back.full_name, "Forrest Gump")
        self.assertEqual(back.given_name, "Forrest")
        self.assertEqual(back.family_name, "Gump")
        self.assertEqual(back.organization, "Bubba Gump Shrimp Co.")
        self.assertEqual(back.job_title, "Shrimp Boat Captain")
        self.assertEqual(back.emails, ["forrestgump@example.com"])
        self.assertEqual(back.phones[0].number, "(111) 555-1212")

    def test_vevent_core_fields_survive(self):
        event = VEVENT(uid="e1", summary="Bastille Day Party",
                       dtstart=datetime(1997, 7, 14, 17, 0, tzinfo=timezone.utc),
                       dtend=datetime(1997, 7, 15, 3, 59, 59, tzinfo=timezone.utc),
                       location="Paris", description="Fireworks")
        back = reparse(event)
        self.assertEqual(back.uid, "e1")
        self.assertEqual(back.summary, "Bastille Day Party")
        self.assertEqual(back.dtstart, event.dtstart)
        self.assertEqual(back.dtend, event.dtend)
        self.assertEqual(back.location, "Paris")
        self.assertEqual(back.description, "Fireworks")

    def test_vtodo_core_fields_survive(self):
        todo = VTODO(uid="t1", summary="File taxes",
                     due=datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc),
                     percent_complete=40, priority=3)
        back = reparse(todo)
        self.assertEqual(back.summary, "File taxes")
        self.assertEqual(back.due, todo.due)
        self.assertEqual(back.percent_complete, 40)
        self.assertEqual(back.priority, 3)

    def test_vjournal_core_fields_survive(self):
        journal = VJOURNAL(uid="j1", summary="Retro",
                           dtstart=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
                           description="What went well")
        back = reparse(journal)
        self.assertEqual(back.summary, "Retro")
        self.assertEqual(back.dtstart, journal.dtstart)
        self.assertEqual(back.description, "What went well")

    def test_vjournal_without_categories_serializes(self):
        # categories defaults to None, which must not be treated as a list.
        journal = VJOURNAL(uid="j1", summary="Bare",
                           dtstart=datetime(2026, 3, 1, 9, 0))
        self.assertIn("BEGIN:VJOURNAL", journal.to_webdav_string())

    def test_alarm_survives(self):
        event = VEVENT(uid="e1", summary="Meeting",
                       dtstart=datetime(2026, 3, 1, 9, 0),
                       alarms=[Alarm(trigger_minutes=30, description="Heads up")])
        back = reparse(event)
        self.assertEqual(len(back.alarms), 1)
        self.assertEqual(back.alarms[0].trigger_minutes, 30)
        self.assertEqual(back.alarms[0].description, "Heads up")

    def test_attendees_survive(self):
        event = VEVENT(uid="e1", summary="Sync",
                       dtstart=datetime(2026, 3, 1, 9, 0),
                       attendees=[
                           Attendee(email="lead@example.com", name="Project Lead",
                                    role="REQ-PARTICIPANT", participation_status="ACCEPTED"),
                           Attendee(email="dev@example.com", name="Developer",
                                    role="OPT-PARTICIPANT", participation_status="NEEDS-ACTION"),
                       ])
        back = reparse(event)
        self.assertEqual([a.email for a in back.attendees],
                         ["lead@example.com", "dev@example.com"])
        self.assertEqual([a.name for a in back.attendees],
                         ["Project Lead", "Developer"])
        self.assertEqual([a.participation_status for a in back.attendees],
                         ["ACCEPTED", "NEEDS-ACTION"])


class TestFixtureReserialization(unittest.TestCase):
    """
    Parses each shipped fixture, serializes it back out, and parses it again.
    The two model generations must agree -- this is the check that catches a
    serializer that emits something its own parser cannot read.
    """

    FIXTURES = [
        "TEST_VCARD_SIMPLE", "TEST_VCARD_FOLDED", "TEST_VCARD_RICH",
        "TEST_VEVENT_SIMPLE", "TEST_VEVENT_FOLDED", "TEST_VEVENT_COMPLEX",
        "TEST_VTODO_WITH_ALARM", "TEST_VCALENDAR_MIXED",
    ]

    COMPARED = ("uid", "summary", "description", "location", "dtstart", "dtend",
                "due", "full_name", "given_name", "family_name", "organization",
                "job_title", "notes", "categories", "emails")

    def test_fixtures_survive_reserialization(self):
        for name in self.FIXTURES:
            raw = getattr(testdata, name)
            for original in to_model(raw):
                with self.subTest(fixture=name, uid=original.uid):
                    back = reparse(original)
                    self.assertEqual(type(back), type(original))
                    for field in self.COMPARED:
                        if not hasattr(original, field):
                            continue
                        self.assertEqual(
                            getattr(back, field), getattr(original, field),
                            f"{name}: field {field!r} did not survive")

    def test_reserialized_fixtures_are_well_formed(self):
        for name in self.FIXTURES:
            for original in to_model(getattr(testdata, name)):
                data = original.to_webdav_string()
                with self.subTest(fixture=name, uid=original.uid):
                    self.assertTrue(data.startswith("BEGIN:"))
                    self.assertEqual(data.count("\n"), data.count("\r\n"))
                    for line in data.split("\r\n"):
                        self.assertNotEqual(line.strip(), "")
                        self.assertLessEqual(len(line.encode("utf-8")),
                                             ModelUtil.FOLD_LIMIT)


if __name__ == "__main__":
    unittest.main()
