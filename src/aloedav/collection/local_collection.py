from enum import StrEnum
from pydantic import BaseModel
from uuid import uuid4

from aloedav.exceptions import PreconditionFailed, WebDAVError
from aloedav.collection import Collection, ComponentSet, Item

class SyncOp(StrEnum):
    UPDATE = "UPDATE"
    DELETE = "DELETE"

class SyncEntry(BaseModel):
    ordinal: int
    token: str
    op: SyncOp
    item_uid: str

class LocalCollection(Collection):
    sync_table: list[SyncEntry]

    @classmethod
    def create(cls, displayname, description, id, component_set: ComponentSet):
        """
        create
        """
        return cls(uid=id, displayname=displayname, description=description, component_set=component_set)
    
    def delete_item(self, filename:str, etag=None)->bool:
        """
        delete_item
        """
        if not filename in self.items:
            raise WebDAVError(f"Delete failed: Filename \"{filename}\" not found")
        if etag and not item.etag == etag:
            raise PreconditionFailed("Delete failed: ETag mismatch")        
        
        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.DELETE,
            item_uid=self.items[filename].uid
        )

        del self.items[filename]

        self.sync_table.append(sync_entry)
        return True

    def get_item(self, filename:str)->Item:
        """
        get_item
        """
        if not filename in self.items:
            raise WebDAVError(f"Update failed: Filename \"{filename}\" not found")
        return self.items[filename]

    def update_item(self, filename:str, item: Item, etag:str=None) -> bool:
        """
        update_item
        """
        if not filename in self.items:
            raise WebDAVError(f"Update failed: Filename \"{filename}\" not found")
        if etag and not item.etag == etag:
            raise PreconditionFailed("Update failed: ETag mismatch")        

        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.UPDATE,
            item_uid=self.items[filename].uid
        )

        self.items[filename].update(item)

        self.sync_table.append(sync_entry)
        return True

    def insert_item(self, item: Item) -> bool:
        """
        insert_item
        """
        sync_entry = SyncEntry(
            ordinal=len(self.sync_table) + 1,
            token=str(uuid4()),
            op=SyncOp.UPDATE,
            item_uid=item.uid
        )

        item.etag = str(uuid4())
        self.items[item.filename()] = item

        self.sync_table.append(sync_entry)
        return True