from enum import StrEnum
from pydantic import BaseModel
from uuid import uuid4

from aloedav.exceptions import PreconditionFailed, WebDAVError
from aloedav.collection import Collection, ComponentSet, Item
from aloedav.model.m00_constant import CalendarComponents
from aloedav.client import AloeDAV

class RemoteCollection(Collection):

    def __init__(self, client:AloeDAV, collection_id):
        self.client = client
        self.collection_id = collection_id

    @classmethod
    def create_addressbook(cls, client:AloeDAV, display_name:str, description:str, addressbook_id:str):
        client.create_addressbook(display_name, description, addressbook_id)
        return cls(client, addressbook_id)

    @classmethod
    def create_calendar(cls, client:AloeDAV, display_name:str, description:str, calendar_id:str, components:CalendarComponents):
        client.create_calendar(display_name, description, calendar_id, components)
        return cls(client, calendar_id)

    def delete_item(self, filename:str, etag=None)->bool:
        return self.client.delete_object(self.collection_id, filename, etag)

    def get_item(self, filename:str)->Item:
        pass

    def update_item(self, filename:str, item: Item, etag:str=None) -> bool:
        pass

    def insert_item(self, item: Item) -> bool:
        pass