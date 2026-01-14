from enum import StrEnum
from pydantic import BaseModel
from collections.abc import Iterable
from uuid import uuid4

from aloedav.exceptions import PreconditionFailed, WebDAVError
from aloedav.collection import Collection, ComponentSet, Item, CollectionType
from aloedav.model.m00_constant import CalendarComponents
from aloedav.client import AloeDAV

class RemoteCollection(Collection):

    def __init__(self, client:AloeDAV, collection_id):
        self.client = client
        self.collection_id = collection_id

    @classmethod
    def create(cls, displayname, description, id, collection_type:CollectionType, component_set: ComponentSet=None):
        pass

    @classmethod
    def get_or_create_addressbook(cls, client:AloeDAV, display_name:str, description:str, addressbook_id:str):
        client.create_addressbook(display_name, description, addressbook_id)
        return cls(client, addressbook_id)

    @classmethod
    def get_or_create_calendar(cls, client:AloeDAV, display_name:str, description:str, calendar_id:str, components:CalendarComponents):
        client.create_calendar(display_name, description, calendar_id, components)
        return cls(client, calendar_id)

    def refresh_sync_token(self)-> str|None:
        """
        refresh_sync_token

        returns:
        - current sync token
        """
        dav_collection = self.client.fetch_collection(self.collection_id)
        self.synctoken = dav_collection.synctoken

    def sync_collection(self, sync_token: str) -> tuple[list[dict], list[dict], str]:
        """
        sync_collection

        returns:
        - dict with keys:
            + "deleted": list of dict for deleted entries with keys:
                - "uid": uid of entry
                - "filename": filename of entry
            + "updated": list of dict for updated entries with keys:
                - "uid": uid of entry
                - "filename": filename of entry
            + "sync_token": current sync token
        """
        pass

    def delete_item(self, filename:str, etag=None)->bool:
        """
        delete_item
        
        raises:
        - WebDAVError if filename not found
        - PreconditionFailed if ETag mismatch

        returns:
        - True if successful
        """
        pass

    def get_item(self, filename:str)->Item:
        """
        get_item

        returns item
        """
        pass

    def update_item(self, filename:str, item: Item, etag:str=None) -> str:
        """
        update_item

        raises:
        - WebDAVError if filename not found
        - PreconditionFailed if ETag mismatch

        returns: 
        - new etag
        """
        pass

    def insert_item(self, item: Item) -> tuple[str,str]:
        """
        insert_item

        returns tuple[str,str] with [filename, etag]
        """
        pass

    def list_items(self) ->  Iterable[Item]:
        """
        list_items

        returns items
        """
        pass