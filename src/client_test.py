
from os import path
import xmltodict
import requests
from datetime import datetime
from typing import Tuple, Union, List, Dict
from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.model.m00_constant import CalendarComponents, TodoStatus
from aloedav.model.vcard    import VCard
from aloedav.model.vevent   import VEvent
from aloedav.model.vtodo    import VTodo
from aloedav.model.vjournal import VJournal
from aloedav.client import AloeDAV

if __name__ == "__main__":
    import uuid

    def setup_infrastructure(client):
        # 1. Define 'What you want' (Configuration)
        required_collections = [
            {
                "type": "addressbook",
                "id": "addressbook_test",
                "name": "Test Contacts",
                "desc": "A verified addressbook"
            },
            {
                "type": "calendar",
                "id": "calendar_test",
                "name": "Test Calendar",
                "desc": "A verified calendar"
            },
            # Easy to add more here...
        ]

        print("--- Verifying Infrastructure ---")
        
        # 2. Execute the logic loop
        for col in required_collections:
            try:
                if col["type"] == "addressbook":
                    client.create_addressbook(col["name"], col["desc"], col["id"])
                    print(f"[OK] Addressbook: {col['name']}")
                    
                elif col["type"] == "calendar":
                    client.create_calendar(col["name"], col["desc"], col["id"])
                    print(f"[OK] Calendar:    {col['name']}")
                    
            except AloeDAVClientError as e:
                # 3. Handle actual failures (Auth, 500s, etc) distinctly from "already exists"
                print(f"[ERR] Failed to ensure {col['name']} ({col['id']}): {e}")
                # In production, you might raise here to stop the app if a critical collection fails
                # raise RuntimeError(f"Critical infrastructure missing: {col['id']}") from e

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  # If your server requires a password, add it here.
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    # try:
    #     aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    # except WebDAVError as e:
    #     print(e)

    # try:
    #     aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    # except WebDAVError as e:
    #     print(e)

    setup_infrastructure(aloedav)
    
    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook Lifecycle
    print("\n--- Testing Addressbook Lifecycle ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Delete Me",
        given_name="Delete",
        family_name="Me",
        emails=["delete.me@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # List & Verify ETag
    entries = aloedav.list_addressbook_entries(abook_id)
    target_entry = next((e for e in entries if fname in e['href']), None)
    
    if target_entry:
        print(f"Found in list. Href: {target_entry['href']}, ETag: {target_entry.get('etag')}")
        
        # Get specific object
        clean_name = aloedav._extract_name_from_href(target_entry['href'])
        content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        print(f"Fetched directly. ETag matches: {etag == target_entry.get('etag')}")

        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        contact.given_name = "UpdatedName"
        if aloedav.update_vcard(abook_id, clean_name, contact, etag=etag):
            print("Update successful.")
            # Refresh ETag after update for deletion
            content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")

        # Delete
        print(f"Deleting {clean_name} with ETag {etag}...")
        success = aloedav.delete_object(abook_id, clean_name, etag=etag)
        if success: 
            print("Deletion successful.")
        else:
            print("Deletion failed.")
    else:
        print("Error: Created contact not found in list.")

    # 3. Test Calendar Lifecycle
    print("\n--- Testing Calendar Lifecycle ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="Temporary Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname}")

    # List with Time Filter
    print("Listing events between 2026-01-09 and 2026-01-11...")
    events = aloedav.list_calendar_objects(
        cal_id, 
        start=datetime(2026, 1, 9), 
        end=datetime(2026, 1, 11)
    )
    
    target_event = next((e for e in events if fname in e['href']), None)
    
    if target_event:
        print(f"Found event. ETag: {target_event.get('etag')}")
        
        # Get
        clean_name = aloedav._extract_name_from_href(target_event['href'])
        content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        
        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        event.summary = "Updated Summary"
        if aloedav.update_calendar_object(cal_id, clean_name, event, etag=etag):
            print("Update successful.")
            content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")
        
        # Delete
        print(f"Deleting {clean_name}...")
        aloedav.delete_object(cal_id, clean_name, etag=etag)
    else:
        print("Error: Created event not found in time-filtered list.")

    # outputs:
    # >--- Setting up Collections ---
    # >Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # >Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # ><error xmlns="DAV:"><resource-must-be-null /></error>
    # >Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # >------------------------------
    # >
    # >--- Testing Addressbook Lifecycle ---
    # >vCard created: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Created Contact: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Found in list. Href: /test/addressbook_test/e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf, ETag: b34cb7b5331f2cfa1601719d84d597ef4971fd68b9f9b9bfb30caaef481f7cd5
    # >Fetched directly. ETag matches: True
    # >Updating e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf (checking ETag logic)...
    # >vCard updated: e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Update successful.
    # >Deleting e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf with ETag 8fb77052daf1b9173e775826097807733b9d0fdde37c610cabf62ea18cde00cd...
    # >Deleted e8fd2152-aa0a-4dc6-8a54-9097d1a50c5f.vcf
    # >Deletion successful.
    # >
    # >--- Testing Calendar Lifecycle ---
    # >Calendar object created: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Created Event: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Listing events between 2026-01-09 and 2026-01-11...
    # >Found event. ETag: a8181286c8949c13c76077c6d5d123997fbcd85002b0832c5921eea289906494
    # >Updating event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics (checking ETag logic)...
    # >Calendar object updated: event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics
    # >Update successful.
    # >Deleting event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics...
    # >Deleted event-d25e58a8-0291-4773-9c31-ef1980ae6acd.ics

if __name__ == "__main__":
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  # If your server requires a password, add it here.
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    # try:
    #     aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    # except WebDAVError as e:
    #     print(e)

    # try:
    #     aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    # except WebDAVError as e:
    #     print(e)

    setup_infrastructure(aloedav)
    
    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook Lifecycle
    print("\n--- Testing Addressbook Lifecycle ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Delete Me",
        given_name="Delete",
        family_name="Me",
        emails=["delete.me@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # List & Verify ETag
    entries = aloedav.list_addressbook_entries(abook_id)
    target_entry = next((e for e in entries if fname in e['href']), None)
    
    if target_entry:
        print(f"Found in list. Href: {target_entry['href']}, ETag: {target_entry.get('etag')}")
        
        # Get specific object
        clean_name = aloedav._extract_name_from_href(target_entry['href'])
        content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        print(f"Fetched directly. ETag matches: {etag == target_entry.get('etag')}")

        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        contact.given_name = "UpdatedName"
        if aloedav.update_vcard(abook_id, clean_name, contact, etag=etag):
            print("Update successful.")
            # Refresh ETag after update for deletion
            content, etag = aloedav.get_addressbook_object(abook_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")

        # Delete
        print(f"Deleting {clean_name} with ETag {etag}...")
        success = aloedav.delete_object(abook_id, clean_name, etag=etag)
        if success: 
            print("Deletion successful.")
        else:
            print("Deletion failed.")
    else:
        print("Error: Created contact not found in list.")


    # 3. Test Calendar Lifecycle
    print("\n--- Testing Calendar Lifecycle ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="Temporary Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname}")

    # List with Time Filter
    print("Listing events between 2026-01-09 and 2026-01-11...")
    events = aloedav.list_calendar_objects(
        cal_id, 
        start=datetime(2026, 1, 9), 
        end=datetime(2026, 1, 11)
    )
    
    target_event = next((e for e in events if fname in e['href']), None)
    
    if target_event:
        print(f"Found event. ETag: {target_event.get('etag')}")
        
        # Get
        clean_name = aloedav._extract_name_from_href(target_event['href'])
        content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        
        # Update
        print(f"Updating {clean_name} (checking ETag logic)...")
        event.summary = "Updated Summary"
        if aloedav.update_calendar_object(cal_id, clean_name, event, etag=etag):
            print("Update successful.")
            content, etag = aloedav.get_calendar_object(cal_id, clean_name)
        else:
            print("Update failed (Expected if ETag quoting is missing).")
        
        # Delete
        print(f"Deleting {clean_name}...")
        aloedav.delete_object(cal_id, clean_name, etag=etag)
    else:
        print("Error: Created event not found in time-filtered list.")

if __name__ == "__main__":
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"

    # try:
    #     aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    # except WebDAVError as e:
    #     print(e)

    # try:
    #     aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    # except WebDAVError as e:
    #     print(e)

    setup_infrastructure(aloedav)

    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Addressbook (Object Retrieval)
    print("\n--- Testing Addressbook High-Level Retrieval ---")
    
    # Create
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        uid=contact_uid,
        fn="Deserialization Test",
        given_name="Deserialization",
        family_name="Test",
        emails=["test@example.com"]
    )
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"Created Contact: {fname}")

    # Retrieve using High-Level Getter
    retrieved_contact, etag = aloedav.get_vcard(abook_id, fname)
    
    if retrieved_contact:
        print(f"Retrieved Object Type: {type(retrieved_contact).__name__}")
        print(f"Retrieved FN: {retrieved_contact.full_name}")
        print(f"ETag: {etag}")
        
        if retrieved_contact.full_name == "Deserialization Test":
            print("[PASS] VCard deserialized successfully.")
        else:
            print("[FAIL] VCard data mismatch.")
            
        # Clean up
        aloedav.delete_object(abook_id, fname, etag=etag)
    else:
        print("[FAIL] Could not retrieve VCard.")


    # 3. Test Calendar (Object Retrieval)
    print("\n--- Testing Calendar High-Level Retrieval ---")
    
    # Create Event
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="High Level Event",
        dtstart=datetime(2026, 1, 10, 12, 0, 0),
        dtend=datetime(2026, 1, 10, 13, 0, 0)
    )
    fname_evt = aloedav.create_calendar_object(cal_id, event)
    print(f"Created Event: {fname_evt}")

    # Create Todo
    todo_uid = f"todo-{uuid.uuid4()}"
    todo = VTodo(
        uid=todo_uid,
        summary="High Level Todo",
        dtstart=datetime(2026, 1, 12, 9, 0, 0),
        status=TodoStatus.NEEDS_ACTION
    )
    fname_todo = aloedav.create_calendar_object(cal_id, todo)
    print(f"Created Todo: {fname_todo}")

    # Retrieve Event
    retrieved_evt, etag_evt = aloedav.get_calendar_model(cal_id, fname_evt)
    if isinstance(retrieved_evt, VEvent):
        print(f"[PASS] Retrieved object is VEvent ({retrieved_evt.summary}).")
        aloedav.delete_object(cal_id, fname_evt, etag=etag_evt)
    else:
        print(f"[FAIL] Expected VEvent, got {type(retrieved_evt)}")

    # Retrieve Todo
    retrieved_todo, etag_todo = aloedav.get_calendar_model(cal_id, fname_todo)
    if isinstance(retrieved_todo, VTodo):
        print(f"[PASS] Retrieved object is VTodo ({retrieved_todo.summary}).")
        aloedav.delete_object(cal_id, fname_todo, etag=etag_todo)
    else:
        print(f"[FAIL] Expected VTodo, got {type(retrieved_todo)}")

    # outputs:

    # > --- Setting up Collections ---
    # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # > <error xmlns="DAV:"><resource-must-be-null /></error>
    # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # > ------------------------------
    # > 
    # > --- Testing Addressbook Lifecycle ---
    # > vCard created: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Created Contact: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Found in list. Href: /test/addressbook_test/7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf, ETag: 43ab5175234c1ab16e637fe1ebd30785f5e232e50fc7231e2424152cc7cf71af
    # > Fetched directly. ETag matches: True
    # > Updating 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf (checking ETag logic)...
    # > vCard updated: 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Update successful.
    # > Deleting 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf with ETag bb6a4d4f5dfd1ee4d5b2aa2cdc62e21ec2c1fa890634ea5a1ab07af405c9efba...
    # > Deleted 7eebccb1-978e-4060-85b6-8abdec1f7fac.vcf
    # > Deletion successful.
    # > 
    # > --- Testing Calendar Lifecycle ---
    # > Calendar object created: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Created Event: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Listing events between 2026-01-09 and 2026-01-11...
    # > Found event. ETag: 3dac627d1fdcd9544684a11367e287d98aebbe79207cb13e49dae899da488025
    # > Updating event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics (checking ETag logic)...
    # > Calendar object updated: event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > Update successful.
    # > Deleting event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics...
    # > Deleted event-d1db569f-3b9e-4651-9aa8-c3e9b89aa5fe.ics
    # > --- Setting up Collections ---
    # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
    # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
    # > <error xmlns="DAV:"><resource-must-be-null /></error>
    # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
    # > ------------------------------
    # > 
    # > --- Testing Addressbook High-Level Retrieval ---
    # > vCard created: 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > Created Contact: 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > Retrieved Object Type: VCard
    # > Retrieved FN: Deserialization Test
    # > ETag: 46457b4dea7f73b2deb66c7288b286870154acb04a0b56e9be5b9ed6e3ecee7a
    # > [PASS] VCard deserialized successfully.
    # > Deleted 1b5abcdb-cbbf-414f-9c33-838b7f4306bf.vcf
    # > 
    # > --- Testing Calendar High-Level Retrieval ---
    # > Calendar object created: event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > Created Event: event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > Calendar object created: todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics
    # > Created Todo: todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics
    # > [PASS] Retrieved object is VEvent (High Level Event).
    # > Deleted event-b5ace01d-f0f9-4d62-bc65-dabd419252cf.ics
    # > [PASS] Retrieved object is VTodo (High Level Todo).
    # > Deleted todo-1bd1178b-981d-4260-a2e4-8fc332ebd9f2.ics



if __name__ == "__main__":
    import uuid

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  
    
    # Init Client
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)

    # 1. Setup Collections
    print("--- Setting up Collections ---")
    abook_id = "addressbook_test"
    cal_id = "calendar_test"
    
    # try:
    #     aloedav.create_addressbook("Test Contacts", "A verified addressbook", abook_id)
    # except WebDAVError as e:
    #     print(e)

    # try:
    #     aloedav.create_calendar("Test Calendar", "A verified calendar", cal_id)
    # except WebDAVError as e:
    #     print(e)

    setup_infrastructure(aloedav)

    print("Collections available:", [c[0] for c in aloedav.list_collections()])
    print("-" * 30)

    # 2. Test Sync Token Lifecycle (Calendar)
    print("\n--- Testing Calendar Sync Token Lifecycle ---")
    
    # A. Initial Sync (Get Baseline)
    # Get current token to ignore previous mess
    current_token = aloedav.get_sync_token(cal_id)
    print(f"Initial Sync Token: {current_token}")
    
    # Run a sync from this token (Should be empty if nothing changed, or catch up)
    updated, deleted, token_1 = aloedav.sync_collection(cal_id, current_token)
    print(f"Baseline Sync: {len(updated)} updated, {len(deleted)} deleted. Token: {token_1}")

    # B. Create Item
    print("\n[Action] Creating Event...")
    event_uid = f"event-{uuid.uuid4()}"
    event = VEvent(
        uid=event_uid,
        summary="Sync Test Event",
        dtstart=datetime(2026, 1, 15, 10, 0, 0)
    )
    fname = aloedav.create_calendar_object(cal_id, event)
    
    # C. Sync (Should see 1 update)
    print("\n[Action] Syncing...")
    updated, deleted, token_2 = aloedav.sync_collection(cal_id, token_1)
    print(f"Sync Result: {len(updated)} updated, {len(deleted)} deleted. Token: {token_2}")
    
    found_create = next((item for item in updated if fname in item['href']), None)
    if found_create:
        print(f"[PASS] Found created event in sync report: {fname}")
        etag_for_delete = found_create['etag']
    else:
        print(f"[FAIL] Created event {fname} NOT found in sync report.")
        etag_for_delete = None

    # D. Delete Item
    if etag_for_delete:
        print("\n[Action] Deleting Event...")
        aloedav.delete_object(cal_id, fname, etag=etag_for_delete)
        
        # E. Sync (Should see 1 delete)
        print("\n[Action] Syncing...")
        updated, deleted, token_3 = aloedav.sync_collection(cal_id, token_2)
        print(f"Sync Result: {len(updated)} updated, {len(deleted)} deleted. Token: {token_3}")
        
        found_delete = next((href for href in deleted if fname in href), None)
        if found_delete:
            print(f"[PASS] Found deleted event href in sync report.")
        else:
            print(f"[FAIL] Deleted event href NOT found in sync report.")

        # Outputs:

        # > --- Setting up Collections ---
        # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
        # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
        # > <error xmlns="DAV:"><resource-must-be-null /></error>
        # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
        # > ------------------------------
        # > 
        # > --- Testing Addressbook High-Level Retrieval ---
        # > vCard created: 3d1e8fde-cd98-43cf-b11e-7c61f8580b4a.vcf
        # > Created Contact: 3d1e8fde-cd98-43cf-b11e-7c61f8580b4a.vcf
        # > Retrieved Object Type: VCard
        # > Retrieved FN: Deserialization Test
        # > ETag: 0b05fae658312027aea4ba1c3a33ee736978c93525107851ccef64de1a85030b
        # > [PASS] VCard deserialized successfully.
        # > Deleted 3d1e8fde-cd98-43cf-b11e-7c61f8580b4a.vcf
        # > 
        # > --- Testing Calendar High-Level Retrieval ---
        # > Calendar object created: event-cb107266-b3af-4465-93cd-1300e8f824df.ics
        # > Created Event: event-cb107266-b3af-4465-93cd-1300e8f824df.ics
        # > Calendar object created: todo-520b16ab-88c6-4173-a73c-4a73c0b4b08b.ics
        # > Created Todo: todo-520b16ab-88c6-4173-a73c-4a73c0b4b08b.ics
        # > [PASS] Retrieved object is VEvent (High Level Event).
        # > Deleted event-cb107266-b3af-4465-93cd-1300e8f824df.ics
        # > [PASS] Retrieved object is VTodo (High Level Todo).
        # > Deleted todo-520b16ab-88c6-4173-a73c-4a73c0b4b08b.ics
        # > --- Setting up Collections ---
        # > Create Collection 'http://vera-webdav-svc.vera.svc.cluster.local:5232/test/addressbook_test' already exists.
        # > Create Collection Failed: 409 - <?xml version='1.0' encoding='utf-8'?>
        # > <error xmlns="DAV:"><resource-must-be-null /></error>
        # > Collections available: ['/test/calendar123/', '/test/calendar_test/', '/test/main2/', '/test/contacts2/', '/test/calendar_id/', '/test/addressbook123/', '/test/addressbook_test/', '/test/addressbook_id/', '/test/contacts/']
        # > ------------------------------
        # > 
        # > --- Testing Calendar Sync Token Lifecycle ---
        # > Initial Sync Token: http://radicale.org/ns/sync/b18dfe4c6fbb2b497c842e6180cd6835b8e266e9c4d222b72be7866d05087202
        # > Baseline Sync: 0 updated, 0 deleted. Token: http://radicale.org/ns/sync/b18dfe4c6fbb2b497c842e6180cd6835b8e266e9c4d222b72be7866d05087202
        # > 
        # > [Action] Creating Event...
        # > Calendar object created: event-77cc1225-b138-4348-a04c-6d38d25967dd.ics
        # > 
        # > [Action] Syncing...
        # > Sync Result: 1 updated, 0 deleted. Token: http://radicale.org/ns/sync/57b4bf733c9ebd992ae3b011b0d82d7d980db9864ab1f69d0e40bf8d995367f8
        # > [PASS] Found created event in sync report: event-77cc1225-b138-4348-a04c-6d38d25967dd.ics
        # > 
        # > [Action] Deleting Event...
        # > Deleted event-77cc1225-b138-4348-a04c-6d38d25967dd.ics
        # > 
        # > [Action] Syncing...
        # > Sync Result: 0 updated, 1 deleted. Token: http://radicale.org/ns/sync/f1233be045d50c2062eb8e30dea68985a1270573c4d8529660492c4283856dec
        # > [PASS] Found deleted event href in sync report.


if __name__ == "__main__":
    import uuid
    from aloedav.model.vcard import VCard

    # Configuration
    RADICALE_HOST = "http://vera-webdav-svc.vera.svc.cluster.local:5232"
    USERNAME = "test"
    PASSWORD = ""  
    
    aloedav = AloeDAV(RADICALE_HOST, USERNAME, PASSWORD)
    abook_id = "addressbook_test"

    print("--- Testing Property Persistence ---")
    
    # 1. Setup VCard with an Extended Attribute (Internal X-Header)
    contact_uid = str(uuid.uuid4())
    contact = VCard(
        fn="Metadata Tester",
        extended_attributes={
            "X-VERA-EMOTION": "Happy",
            "X-VERA-IMPORTANCE": "High"
        }
    )
    
    fname = aloedav.create_vcard(abook_id, contact)
    print(f"[Action] Created Contact: {fname}")

    # 2. Retrieve Fresh State
    print("\n--- Retrieving Fresh State from Server ---")
    retrieved_vcard, etag = aloedav.get_vcard(abook_id, fname)

    # 3. Assertions
    print(f"Retrieved ETag: {etag}")
    
    # Verify Internal Extended Attributes
    if retrieved_vcard.extended_attributes.get("X-VERA-EMOTION") == "Happy":
        print("[PASS] Extended Attribute (X-Header) persisted.")
    else:
        print(f"[FAIL] Extended Attribute missing. Found: {retrieved_vcard.extended_attributes}")

    # 4. Cleanup
    print("\n[Action] Cleaning up...")
    aloedav.delete_object(abook_id, fname, etag=etag)
    print("Test Complete.")

# outputs:

# > --- Testing Property Persistence ---
# > [Action] Created Contact: 7d05b393-6905-4d93-9d91-a20179028f39.vcf
# > 
# > --- Retrieving Fresh State from Server ---
# > Retrieved ETag: 69401c872095c6633f566f4d6f6e54c77bcb4bf0ed2456b3253a2fdb88f08177
# > [PASS] Extended Attribute (X-Header) persisted.
# > 
# > [Action] Cleaning up...
# > Test Complete.
