"""
Storage tests.

The load-bearing property is that the store's unit is the resource. Keying by
component is the defect that destroys a recurring series, and storage is where
it would do the most damage, since this is the server's actual memory.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aloedav.collection import CollectionType, ComponentSet
from aloedav.model.serial_util import to_resource
from aloedav.storage import (AlreadyExists, CollectionNotFound, EtagMismatch,
                             ResourceNotFoundInStore, StorageError,
                             SyncTokenExpired)
from aloedav.storage.file_store import FileStore, compute_etag

NY = "America/New_York"

SERIES = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:standup@x", "SUMMARY:Standup",
    f"DTSTART;TZID={NY}:20260302T090000",
    "RRULE:FREQ=WEEKLY;BYDAY=MO", "END:VEVENT",
    "BEGIN:VEVENT", "UID:standup@x",
    f"RECURRENCE-ID;TZID={NY}:20260309T090000",
    f"DTSTART;TZID={NY}:20260309T110000",
    "SUMMARY:Standup (moved)", "END:VEVENT",
    "END:VCALENDAR"])

SIMPLE = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//T//EN",
    "BEGIN:VEVENT", "UID:one@x", "SUMMARY:One",
    "DTSTART:20260302T090000Z", "END:VEVENT", "END:VCALENDAR"])

CARD = "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", "UID:ada@x",
                    "FN:Ada Lovelace", "N:Lovelace;Ada;;;", "END:VCARD"])


class StoreTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = FileStore(self.root)
        self.store.create_collection("alice", "work", CollectionType.CALENDAR,
                                     "Work", "desc")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, body=SIMPLE, **kw):
        return self.store.put_resource("alice", "work", to_resource(body), **kw)


class TestCollections(StoreTest):

    def test_created_collection_is_listed(self):
        [info] = self.store.list_collections("alice")
        self.assertEqual(info.displayname, "Work")
        self.assertIs(info.collection_type, CollectionType.CALENDAR)

    def test_users_are_discovered_from_disk(self):
        self.store.create_collection("bob", "cal", CollectionType.CALENDAR)
        self.assertEqual(self.store.users(), ["alice", "bob"])

    def test_component_set_survives_a_round_trip(self):
        self.store.create_collection("alice", "book", CollectionType.ADDRESSBOOK)
        info = self.store.get_collection("alice", "book")
        self.assertIs(info.component_set, ComponentSet.VCONTACT)

    def test_creating_twice_is_refused(self):
        with self.assertRaises(AlreadyExists):
            self.store.create_collection("alice", "work", CollectionType.CALENDAR)

    def test_missing_collection_raises(self):
        with self.assertRaises(CollectionNotFound):
            self.store.get_collection("alice", "nope")

    def test_delete_removes_it(self):
        self.store.delete_collection("alice", "work")
        self.assertEqual(self.store.list_collections("alice"), [])

    def test_unknown_user_lists_nothing_rather_than_raising(self):
        self.assertEqual(self.store.list_collections("nobody"), [])


class TestResourcesAreTheUnit(StoreTest):

    def test_master_and_override_are_stored_as_one_file(self):
        # The defect this layer exists to avoid: keyed by component, these two
        # share a UID, collide on filename, and one silently overwrites the other.
        self.put(SERIES)
        files = [p.name for p in Path(self.root, "alice", "work").iterdir()
                 if p.suffix == ".ics"]
        self.assertEqual(files, ["standup@x.ics"])

        [resource] = self.store.list_resources("alice", "work")
        self.assertEqual(len(resource.components), 2)
        self.assertEqual(resource.master.summary, "Standup")
        self.assertEqual(resource.overrides[0].summary, "Standup (moved)")

    def test_reading_back_preserves_the_zone(self):
        self.put(SERIES)
        resource = self.store.get_resource("alice", "work", "standup@x.ics")
        self.assertEqual(resource.master.dtstart.tzid, NY)

    def test_stored_name_is_reported(self):
        self.put(SIMPLE)
        [resource] = self.store.list_resources("alice", "work")
        self.assertEqual(resource.stored_name, "one@x.ics")

    def test_vcard_resource_round_trips(self):
        self.store.create_collection("alice", "book", CollectionType.ADDRESSBOOK)
        self.store.put_resource("alice", "book", to_resource(CARD))
        [resource] = self.store.list_resources("alice", "book")
        self.assertEqual(resource.card.full_name, "Ada Lovelace")


class TestEtags(StoreTest):

    def test_etag_is_derived_from_content(self):
        etag = self.put(SIMPLE)
        self.assertEqual(etag, compute_etag(
            to_resource(SIMPLE).to_webdav_string()))

    def test_identical_rewrite_keeps_the_etag(self):
        # A no-op write must not look like a change, or every syncing client
        # gets handed pointless work.
        first = self.put(SIMPLE)
        self.assertEqual(self.put(SIMPLE), first)

    def test_identical_rewrite_records_no_change(self):
        self.put(SIMPLE)
        token = self.store.get_collection("alice", "work").sync_token
        self.put(SIMPLE)
        self.assertEqual(self.store.get_collection("alice", "work").sync_token, token)

    def test_etag_survives_a_new_store_instance(self):
        etag = self.put(SIMPLE)
        fresh = FileStore(self.root)
        self.assertEqual(fresh.get_resource("alice", "work", "one@x.ics").etag, etag)

    def test_if_match_mismatch_is_refused(self):
        self.put(SIMPLE)
        with self.assertRaises(EtagMismatch):
            self.put(SERIES, filename="one@x.ics", if_match="wrong")

    def test_if_match_success(self):
        etag = self.put(SIMPLE)
        self.put(SERIES, filename="one@x.ics", if_match=etag)
        self.assertEqual(
            self.store.get_resource("alice", "work", "one@x.ics").master.summary,
            "Standup")

    def test_if_none_match_refuses_an_overwrite(self):
        self.put(SIMPLE)
        with self.assertRaises(AlreadyExists):
            self.put(SERIES, filename="one@x.ics", if_none_match=True)

    def test_delete_honours_if_match(self):
        etag = self.put(SIMPLE)
        with self.assertRaises(EtagMismatch):
            self.store.delete_resource("alice", "work", "one@x.ics", if_match="wrong")
        self.store.delete_resource("alice", "work", "one@x.ics", if_match=etag)
        with self.assertRaises(ResourceNotFoundInStore):
            self.store.get_resource("alice", "work", "one@x.ics")


class TestSync(StoreTest):

    def test_initial_sync_reports_everything(self):
        self.put(SIMPLE)
        self.put(SERIES)
        result = self.store.sync("alice", "work")
        self.assertTrue(result.is_initial)
        self.assertEqual(len(result.changes), 2)

    def test_delta_reports_only_what_changed(self):
        self.put(SIMPLE)
        token = self.store.get_collection("alice", "work").sync_token
        self.put(SERIES)
        result = self.store.sync("alice", "work", token)
        self.assertEqual([c.filename for c in result.changes], ["standup@x.ics"])
        self.assertFalse(result.is_initial)

    def test_deletion_is_reported(self):
        self.put(SIMPLE)
        token = self.store.get_collection("alice", "work").sync_token
        self.store.delete_resource("alice", "work", "one@x.ics")
        [change] = self.store.sync("alice", "work", token).changes
        self.assertTrue(change.deleted)

    def test_repeated_edits_collapse_to_one_change(self):
        token = self.store.get_collection("alice", "work").sync_token
        self.put(SIMPLE)
        self.put(SERIES, filename="one@x.ics")
        self.assertEqual(len(self.store.sync("alice", "work", token).changes), 1)

    def test_unknown_token_is_rejected_rather_than_answered(self):
        # RFC 6578 3.2: the client must be told to resync, not handed a partial
        # answer that leaves it quietly stale.
        with self.assertRaises(SyncTokenExpired):
            self.store.sync("alice", "work", "no-such-token")

    def test_ctag_changes_when_content_changes(self):
        before = self.store.get_collection("alice", "work").ctag
        self.put(SIMPLE)
        self.assertNotEqual(self.store.get_collection("alice", "work").ctag, before)

    def test_sync_log_is_bounded(self):
        from aloedav.storage import file_store
        original = file_store.SYNC_LOG_LIMIT
        file_store.SYNC_LOG_LIMIT = 5
        try:
            for index in range(12):
                body = SIMPLE.replace("SUMMARY:One", f"SUMMARY:One {index}")
                self.put(body)
            metadata = json.loads(
                Path(self.root, "alice", "work", "collection.json").read_text())
            self.assertLessEqual(len(metadata["sync_log"]), 5)
        finally:
            file_store.SYNC_LOG_LIMIT = original


class TestSafety(StoreTest):

    def test_path_traversal_is_refused(self):
        for bad in ["../../etc/passwd", "..", "a/b", "a\\b", ".hidden"]:
            with self.assertRaises(StorageError, msg=bad):
                self.store.get_resource("alice", "work", bad)

    def test_metadata_file_cannot_be_clobbered(self):
        with self.assertRaises(StorageError):
            self.put(SIMPLE, filename="collection.json")

    def test_traversal_via_user_or_collection_is_refused(self):
        with self.assertRaises(StorageError):
            self.store.list_collections("../..")
        with self.assertRaises(StorageError):
            self.store.get_collection("alice", "../other")

    def test_unparseable_file_is_skipped_not_deleted(self):
        # Leaving it on disk matters: this project's whole premise is that
        # content it cannot read is not content it may destroy.
        junk = Path(self.root, "alice", "work", "junk.ics")
        junk.write_text("this is not iCalendar at all")
        self.put(SIMPLE)
        names = [r.stored_name for r in self.store.list_resources("alice", "work")]
        self.assertEqual(names, ["one@x.ics"])
        self.assertTrue(junk.exists())

    def test_stored_bytes_are_readable_on_disk(self):
        # The reason for choosing a filesystem layout in the first place.
        self.put(SERIES)
        body = Path(self.root, "alice", "work", "standup@x.ics").read_text()
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn(f"DTSTART;TZID={NY}:20260302T090000", body)


if __name__ == "__main__":
    unittest.main()
