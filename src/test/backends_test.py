"""
Backend selection and migration tests.

Two properties matter here. Data must survive a move between backends
unchanged -- byte for byte, since a migration that tidied its input would be
the silent rewriting this project exists to prevent. And after a move, an
ordinary run must open what was migrated *into*, not the source left beside it;
that failure would look like everything working while serving stale data.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from aloedav.collection import CollectionType
from aloedav.model.serial_util import to_resource
from aloedav.storage.backends import (ALOELITE, FILE, detect_backend, migrate,
                                      open_store, set_active_backend)
from aloedav.storage.aloelite_store import AloeliteStore
from aloedav.storage.file_store import FileStore
from aloedav.web.__main__ import main as cli_main, seed

NY = "America/New_York"

SERIES = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VTIMEZONE", "TZID:America/New_York", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:standup@x", "SUMMARY:Standup",
    f"DTSTART;TZID={NY}:20260302T090000",
    "RRULE:FREQ=WEEKLY;BYDAY=MO",
    f"EXDATE;TZID={NY}:20260316T090000",
    "X-VENDOR-THING:keep me", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@x",
    f"RECURRENCE-ID;TZID={NY}:20260309T090000",
    f"DTSTART;TZID={NY}:20260309T110000",
    "SUMMARY:Standup (moved)", "END:VEVENT",
    "END:VCALENDAR"])


class BackendTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def closing(self, store):
        self.addCleanup(lambda: getattr(store, "close", lambda: None)())
        return store


class TestSelection(BackendTest):

    def test_aloelite_is_the_default(self):
        store = self.closing(open_store(self.root))
        self.assertIsInstance(store, AloeliteStore)

    def test_file_backend_is_one_flag_away(self):
        store = self.closing(open_store(self.root, FILE))
        self.assertIsInstance(store, FileStore)

    def test_unknown_backend_is_refused(self):
        with self.assertRaises(ValueError):
            open_store(self.root, "postgres")

    def test_file_backend_refuses_a_pin_rather_than_ignoring_it(self):
        # Silently storing unencrypted data for someone who asked for
        # encryption would be the worst possible response.
        with self.assertRaises(ValueError):
            open_store(self.root, FILE, pin=b"secret")

    def test_empty_root_detects_nothing(self):
        self.assertIsNone(detect_backend(self.root))

    def test_existing_aloelite_store_is_detected(self):
        self.closing(open_store(self.root)).create_collection(
            "alice", "work", CollectionType.CALENDAR)
        self.assertEqual(detect_backend(self.root), ALOELITE)

    def test_existing_file_store_is_detected(self):
        open_store(self.root, FILE).create_collection(
            "alice", "work", CollectionType.CALENDAR)
        self.assertEqual(detect_backend(self.root), FILE)

    def test_recorded_choice_beats_what_is_on_disk(self):
        self.closing(open_store(self.root)).create_collection(
            "alice", "work", CollectionType.CALENDAR)
        set_active_backend(self.root, FILE)
        self.assertEqual(detect_backend(self.root), FILE)

    def test_a_meaningless_marker_is_ignored(self):
        Path(self.root, "active-backend").write_text("nonsense\n")
        self.closing(open_store(self.root)).create_collection(
            "alice", "work", CollectionType.CALENDAR)
        self.assertEqual(detect_backend(self.root), ALOELITE)


class TestMigration(BackendTest):

    def populate(self, store):
        store.create_collection("alice", "work", CollectionType.CALENDAR,
                                "Work", "a description")
        store.create_collection("bob", "cal", CollectionType.ADDRESSBOOK, "People")
        store.put_resource("alice", "work", to_resource(SERIES))
        return store

    def test_everything_moves(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        moved = migrate(source, target)
        self.assertEqual(moved["collections"], 2)
        self.assertEqual(moved["resources"], 1)
        self.assertEqual(target.users(), ["alice", "bob"])

    def test_bytes_are_identical_after_a_move(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        before = source.get_resource("alice", "work", "standup@x.ics").to_webdav_string()
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        after = target.get_resource("alice", "work", "standup@x.ics").to_webdav_string()
        self.assertEqual(before, after)

    def test_etags_are_unchanged_by_a_move(self):
        # ETags are content hashes, so an identical body must keep its
        # validator across backends.
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        before = source.get_resource("alice", "work", "standup@x.ics").etag
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        self.assertEqual(target.get_resource("alice", "work", "standup@x.ics").etag,
                         before)

    def test_unmodelled_content_survives_a_move(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        body = target.get_resource("alice", "work", "standup@x.ics").to_webdav_string()
        for fragment in ["X-VENDOR-THING:keep me", "BEGIN:VTIMEZONE",
                         "CALSCALE:GREGORIAN", f"EXDATE;TZID={NY}:20260316T090000"]:
            self.assertIn(fragment, body)

    def test_collection_metadata_survives_a_move(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        info = target.get_collection("alice", "work")
        self.assertEqual(info.displayname, "Work")
        self.assertEqual(info.description, "a description")
        self.assertIs(info.collection_type, CollectionType.CALENDAR)

    def test_the_series_stays_one_resource(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        [resource] = target.list_resources("alice", "work")
        self.assertEqual(len(resource.components), 2)

    def test_a_round_trip_returns_the_same_bytes(self):
        first = self.closing(self.populate(open_store(self.root, ALOELITE)))
        before = first.get_resource("alice", "work", "standup@x.ics").to_webdav_string()
        middle = self.closing(open_store(self.root, FILE))
        migrate(first, middle)

        back_root = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(back_root, ignore_errors=True))
        last = self.closing(open_store(back_root, ALOELITE))
        migrate(middle, last)
        self.assertEqual(
            last.get_resource("alice", "work", "standup@x.ics").to_webdav_string(),
            before)

    def test_existing_collections_are_skipped_not_clobbered(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        target.create_collection("alice", "work", CollectionType.CALENDAR, "Mine")
        moved = migrate(source, target)
        self.assertEqual(moved["skipped"], 1)
        self.assertEqual(target.get_collection("alice", "work").displayname, "Mine")

    def test_overwrite_writes_into_existing_collections(self):
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        target.create_collection("alice", "work", CollectionType.CALENDAR, "Mine")
        migrate(source, target, overwrite=True)
        self.assertEqual(len(target.list_resources("alice", "work")), 1)

    def test_sync_tokens_do_not_cross(self):
        # A token names a position in a log the target never had. Carrying one
        # over would answer a client from a log that means something else.
        source = self.closing(self.populate(open_store(self.root, ALOELITE)))
        target = self.closing(open_store(self.root, FILE))
        migrate(source, target)
        self.assertNotEqual(target.get_collection("alice", "work").sync_token,
                            source.get_collection("alice", "work").sync_token)


class TestCommandLine(BackendTest):

    def test_migrate_records_the_new_backend(self):
        store = open_store(self.root)
        seed(store)
        store.close()
        self.assertEqual(cli_main(["migrate", "--root", self.root, "--to", "file"]), 0)
        # The source is left in place, so only the marker prevents the next
        # ordinary run from serving it.
        self.assertTrue(Path(self.root, "aloedav.sqlite").exists())
        self.assertEqual(detect_backend(self.root), FILE)

    def test_migrated_data_is_readable_as_plain_files(self):
        store = open_store(self.root)
        seed(store)
        store.close()
        cli_main(["migrate", "--root", self.root, "--to", "file"])
        body = Path(self.root, "collections", "demo", "work",
                    "standup@demo.ics").read_bytes().decode()
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("RRULE:FREQ=WEEKLY", body)

    def test_migrating_to_the_current_backend_is_refused(self):
        store = open_store(self.root)
        seed(store)
        store.close()
        self.assertEqual(cli_main(["migrate", "--root", self.root, "--to", "aloelite"]), 1)

    def test_migrating_an_empty_root_is_refused(self):
        self.assertEqual(cli_main(["migrate", "--root", self.root, "--to", "file"]), 1)


if __name__ == "__main__":
    unittest.main()
