import unittest

from aloedav.exceptions import PreconditionFailed, WebDAVError
from aloedav.collection.local_collection import LocalCollection
from aloedav.model.m00_constant import TodoStatus
from aloedav.model.m02_vcard import VCARD
from aloedav.model.m02_vevent import VEVENT
from aloedav.model.m02_vtodo import VTODO

class TestFuncs(unittest.TestCase):

    def test_create_local_collections(self):

        address_book = LocalCollection.create_addressbook(
            "Test Contacts", 
            "A verified addressbook", 
            "addressbook_test")
        
        calendar = LocalCollection.create_calendar(
            "Test Calendar", 
            "A verified calendar", 
            "calendar_test")

    def test_contact_local_create_update_delete(self):
        from uuid import uuid4

        address_book = LocalCollection.create_addressbook(
            "Test Contacts", 
            "A verified addressbook", 
            "addressbook_test")
        
        initial_sync_token = address_book.get_sync_token()
        
        contact = VCARD(
            uid=f"contact-{uuid4()}",
            fn="Delete Me",
            given_name="Delete",
            family_name="Me",
            emails=["delete.me@example.com"]
        )

        # =====================
        # Insert Contact
        # =====================
        contact_filename, insert_etag = address_book.insert_item(contact)
        with self.assertRaises(WebDAVError):
            address_book.get_item("nonexistant filename")
        contact_entry = address_book.get_item(contact_filename)

        after_insert_sync_obj = address_book.sync_collection(initial_sync_token)
        after_insert_sync_token = after_insert_sync_obj["sync_token"]

        self.assertNotEqual(after_insert_sync_token, initial_sync_token, "Sync token updated after insert")
        self.assertEqual(len(after_insert_sync_obj["updated"]), 1, "Sync collection reports one item updated after insert")
        self.assertEqual(len(after_insert_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after insert")

        self.assertEqual(insert_etag, contact_entry.etag, "Insert etag matches retrieved")
        self.assertEqual(contact_entry.given_name,"Delete", "Inserted given_name matches retrieved")
        
        # =====================
        # Update Contact
        # =====================
        contact_entry.given_name = "UpdatedName"
        with self.assertRaises(PreconditionFailed):
            address_book.update_item(contact_filename, contact_entry, "wrong_etag")

        with self.assertRaises(WebDAVError):
            address_book.update_item("wrong_filename", contact_entry, insert_etag)

        updated_etag = address_book.update_item(contact_filename, contact_entry, insert_etag)
        updated_entry = address_book.get_item(contact_filename)
        after_update_sync_obj = address_book.sync_collection(after_insert_sync_token)
        after_update_sync_token = after_update_sync_obj["sync_token"]

        self.assertNotEqual(initial_sync_token, after_update_sync_token, "Sync token updated after update")
        self.assertEqual(len(after_update_sync_obj["updated"]), 1, "Sync collection reports one item updated after update")
        self.assertEqual(len(after_update_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after update")

        self.assertNotEqual(updated_etag, insert_etag, "Etag updated on vcard update")
        self.assertEqual(updated_entry.given_name,"UpdatedName", "Updated given_name matches retrieved")

        # =====================
        # Delete Contact
        # =====================
        with self.assertRaises(PreconditionFailed):
            address_book.delete_item(contact_filename, "wrong_etag")

        with self.assertRaises(PreconditionFailed):
            address_book.delete_item(contact_filename, insert_etag)

        with self.assertRaises(WebDAVError):
            address_book.delete_item("wrong_filename", updated_etag)

        address_book.delete_item(contact_filename, updated_etag)

        after_delete_sync_obj = address_book.sync_collection(after_update_sync_token)
        after_delete_sync_token = after_delete_sync_obj["sync_token"]

        self.assertNotEqual(after_update_sync_token, after_delete_sync_token, "Sync token updated after delete")
        self.assertEqual(len(after_delete_sync_obj["updated"]), 0, "Sync collection reports no items updated after delete")
        self.assertEqual(len(after_delete_sync_obj["deleted"]), 1, "Sync collection reports one item deleted after delete")

    def test_event_local_create_update_delete(self):
        from uuid import uuid4
        from datetime import datetime
        
        calendar = LocalCollection.create_calendar(
            "Test Calendar", 
            "A verified calendar", 
            "calendar_test")
        
        initial_sync_token = calendar.get_sync_token()

        event = VEVENT(
            uid=f"event-{uuid4()}",
            summary="Temporary Event",
            dtstart=datetime(2026, 1, 10, 12, 0, 0),
            dtend=datetime(2026, 1, 10, 13, 0, 0)
        )

        # =====================
        # Insert Event
        # =====================
        event_filename, insert_etag = calendar.insert_item(event)
        with self.assertRaises(WebDAVError):
            calendar.get_item("nonexistant filename")
        event_entry = calendar.get_item(event_filename)

        after_insert_sync_obj = calendar.sync_collection(initial_sync_token)
        after_insert_sync_token = after_insert_sync_obj["sync_token"]

        self.assertNotEqual(after_insert_sync_token, initial_sync_token, "Sync token updated after insert")
        self.assertEqual(len(after_insert_sync_obj["updated"]), 1, "Sync collection reports one item updated after insert")
        self.assertEqual(len(after_insert_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after insert")

        self.assertEqual(insert_etag, event_entry.etag, "Insert etag matches retrieved")
        self.assertEqual(event_entry.summary,"Temporary Event", "Inserted summary matches retrieved")
        
        # =====================
        # Update Event
        # =====================
        event_entry.summary = "Updated Summary"
        with self.assertRaises(PreconditionFailed):
            calendar.update_item(event_filename, event_entry, "wrong_etag")

        with self.assertRaises(WebDAVError):
            calendar.update_item("wrong_filename", event_entry, insert_etag)

        updated_etag = calendar.update_item(event_filename, event_entry, insert_etag)
        updated_entry = calendar.get_item(event_filename)
        after_update_sync_obj = calendar.sync_collection(after_insert_sync_token)
        after_update_sync_token = after_update_sync_obj["sync_token"]

        self.assertNotEqual(initial_sync_token, after_update_sync_token, "Sync token updated after update")
        self.assertEqual(len(after_update_sync_obj["updated"]), 1, "Sync collection reports one item updated after update")
        self.assertEqual(len(after_update_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after update")

        self.assertNotEqual(updated_etag, insert_etag, "Etag updated on vevent update")
        self.assertEqual(updated_entry.summary, "Updated Summary", "Updated summary matches retrieved")

        # =====================
        # Delete Event
        # =====================
        with self.assertRaises(PreconditionFailed):
            calendar.delete_item(event_filename, "wrong_etag")

        with self.assertRaises(PreconditionFailed):
            calendar.delete_item(event_filename, insert_etag)

        with self.assertRaises(WebDAVError):
            calendar.delete_item("wrong_filename", updated_etag)

        calendar.delete_item(event_filename, updated_etag)

        after_delete_sync_obj = calendar.sync_collection(after_update_sync_token)
        after_delete_sync_token = after_delete_sync_obj["sync_token"]

        self.assertNotEqual(after_update_sync_token, after_delete_sync_token, "Sync token updated after delete")
        self.assertEqual(len(after_delete_sync_obj["updated"]), 0, "Sync collection reports no items updated after delete")
        self.assertEqual(len(after_delete_sync_obj["deleted"]), 1, "Sync collection reports one item deleted after delete")


    def test_task_local_create_update_delete(self):
        from uuid import uuid4
        from datetime import datetime
        
        calendar = LocalCollection.create_calendar(
            "Test Calendar", 
            "A verified calendar", 
            "calendar_test")
        
        initial_sync_token = calendar.get_sync_token()

        task = VTODO(
            uid=f"task-{uuid4()}",
            summary="Temporary Task",
            dtstart=datetime(2026, 1, 10, 12, 0, 0),
            status=TodoStatus.NEEDS_ACTION
        )

        # =====================
        # Insert Task
        # =====================
        task_filename, insert_etag = calendar.insert_item(task)
        with self.assertRaises(WebDAVError):
            calendar.get_item("nonexistant filename")
        task_entry = calendar.get_item(task_filename)

        after_insert_sync_obj = calendar.sync_collection(initial_sync_token)
        after_insert_sync_token = after_insert_sync_obj["sync_token"]

        self.assertNotEqual(after_insert_sync_token, initial_sync_token, "Sync token updated after insert")
        self.assertEqual(len(after_insert_sync_obj["updated"]), 1, "Sync collection reports one item updated after insert")
        self.assertEqual(len(after_insert_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after insert")

        self.assertEqual(insert_etag, task_entry.etag, "Insert etag matches retrieved")
        self.assertEqual(task_entry.summary,"Temporary Task", "Inserted summary matches retrieved")
        
        # =====================
        # Update Task
        # =====================
        task_entry.summary = "Updated Summary"
        with self.assertRaises(PreconditionFailed):
            calendar.update_item(task_filename, task_entry, "wrong_etag")

        with self.assertRaises(WebDAVError):
            calendar.update_item("wrong_filename", task_entry, insert_etag)

        updated_etag = calendar.update_item(task_filename, task_entry, insert_etag)
        updated_entry = calendar.get_item(task_filename)
        after_update_sync_obj = calendar.sync_collection(after_insert_sync_token)
        after_update_sync_token = after_update_sync_obj["sync_token"]

        self.assertNotEqual(initial_sync_token, after_update_sync_token, "Sync token updated after update")
        self.assertEqual(len(after_update_sync_obj["updated"]), 1, "Sync collection reports one item updated after update")
        self.assertEqual(len(after_update_sync_obj["deleted"]), 0, "Sync collection reports no items deleted after update")

        self.assertNotEqual(updated_etag, insert_etag, "Etag updated on vtask update")
        self.assertEqual(updated_entry.summary, "Updated Summary", "Updated summary matches retrieved")

        # =====================
        # Delete Task
        # =====================
        with self.assertRaises(PreconditionFailed):
            calendar.delete_item(task_filename, "wrong_etag")

        with self.assertRaises(PreconditionFailed):
            calendar.delete_item(task_filename, insert_etag)

        with self.assertRaises(WebDAVError):
            calendar.delete_item("wrong_filename", updated_etag)

        calendar.delete_item(task_filename, updated_etag)

        after_delete_sync_obj = calendar.sync_collection(after_update_sync_token)
        after_delete_sync_token = after_delete_sync_obj["sync_token"]

        self.assertNotEqual(after_update_sync_token, after_delete_sync_token, "Sync token updated after delete")
        self.assertEqual(len(after_delete_sync_obj["updated"]), 0, "Sync collection reports no items updated after delete")
        self.assertEqual(len(after_delete_sync_obj["deleted"]), 1, "Sync collection reports one item deleted after delete")