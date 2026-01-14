from enum import StrEnum
from pydantic import BaseModel

from collections.abc import Iterable
from uuid import uuid4

from aloedav.exceptions import PreconditionFailed, WebDAVError
from aloedav.collection import Collection, ComponentSet, Item, CollectionType
from aloedav.model.m00_constant import CalendarComponents

class SyncOp(StrEnum):
    INIT = "INIT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"

class SyncEntry(BaseModel):
    ordinal: int
    token: str
    op: SyncOp
    item_uid: str | None
    filename: str | None

class LocalCollection(Collection):
    sync_table: list[SyncEntry] = []

    @classmethod
    def create(cls, displayname, description, id, collection_type:CollectionType, component_set: ComponentSet=None):
        """
        create
        """
        if not component_set:
            match collection_type:
                case CollectionType.ADDRESSBOOK:
                    component_set = ComponentSet.VCONTACT
                case CollectionType.CALENDAR:
                    component_set = ComponentSet.VJOURNAL | ComponentSet.VTODO | ComponentSet.VEVENT
        collection = cls(uid=id, displayname=displayname, description=description, component_set=component_set, collection_type = collection_type)
    
        sync_entry = SyncEntry(
            ordinal= 1,
            token=str(uuid4()),
            op=SyncOp.INIT,
            item_uid=None,
            filename=None
        )

        collection.sync_table.append(sync_entry)
        return collection
    
    @classmethod
    def create_addressbook(cls, display_name:str, description:str, addressbook_id:str):
        return cls.create(display_name, description, addressbook_id, CollectionType.ADDRESSBOOK, ComponentSet.VCONTACT)

    @classmethod
    def create_calendar(cls, display_name:str, description:str, calendar_id:str, components:CalendarComponents=None):

        component_set = ComponentSet.INVALID
        if components == None:
            component_set = ComponentSet.VEVENT | ComponentSet.VTODO | ComponentSet.VJOURNAL
        else:
            if CalendarComponents.VEVENT in components:
                component_set |= ComponentSet.VEVENT
            if CalendarComponents.VJOURNAL in components:
                component_set |= ComponentSet.VJOURNAL
            if CalendarComponents.VTODO in components:
                component_set |= ComponentSet.VTODO

        return cls.create(display_name, description, calendar_id, CollectionType.CALENDAR, component_set)

    def get_sync_token(self)-> str|None:
        sync_entry = sorted(self.sync_table, key=lambda sync_entry: sync_entry.ordinal)[-1]
        return sync_entry.token if sync_entry else None
    
    def sync_collection(self, sync_token: str) -> dict:
        prev_sync_entry = next((sync_entry for sync_entry in self.sync_table if sync_entry.token == sync_token))
        updated = []
        deleted = []
        for sync_entry in self.sync_table:
            if sync_entry.ordinal > prev_sync_entry.ordinal:
                match sync_entry.op:
                    case SyncOp.DELETE:
                        deleted.append({"uid" : sync_entry.item_uid, "filename": sync_entry.filename})
                    case SyncOp.UPDATE:
                        updated.append({"uid" : sync_entry.item_uid, "filename": sync_entry.filename})
        return {
            "deleted":deleted, 
            "updated":updated, 
            "sync_token": self.get_sync_token()
        }
    
    def delete_item(self, filename:str, etag=None)->bool:
        """
        delete_item
        """
        if not filename in self.items:
            raise WebDAVError(f"Delete failed: Filename \"{filename}\" not found")
        if etag and not self.items[filename].etag == etag:
            raise PreconditionFailed("Delete failed: ETag mismatch")        
        
        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.DELETE,
            item_uid = self.items[filename].uid,
            filename = filename
        )

        del self.items[filename]

        self.sync_table.append(sync_entry)
        return True

    def get_item(self, filename:str)->Item:
        """
        get_item

        returns item
        """
        if not filename in self.items:
            raise WebDAVError(f"Update failed: Filename \"{filename}\" not found")
        return self.items[filename]

    def update_item(self, filename:str, item: Item, etag:str=None) -> str:
        """
        update_item

        returns new etag
        """
        if not filename in self.items:
            raise WebDAVError(f"Update failed: Filename \"{filename}\" not found")
        if etag and not item.etag == etag:
            raise PreconditionFailed("Update failed: ETag mismatch")        

        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.UPDATE,
            item_uid=self.items[filename].uid,
            filename = filename
        )

        self.items[filename].update(item)

        self.sync_table.append(sync_entry)
        return self.items[filename].etag

    def insert_item(self, item: Item) -> tuple[str, str]:
        """
        insert_item

        returns tuple[str,str] with [filename, etag]
        """
        filename = item.filename()

        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.UPDATE,
            item_uid=item.uid,
            filename=filename
        )

        item.etag = str(uuid4())
        self.items[item.filename()] = item

        self.sync_table.append(sync_entry)
        return filename, self.items[filename].etag
    
    def list_items(self) ->  Iterable[Item]:
        return self.items.values()