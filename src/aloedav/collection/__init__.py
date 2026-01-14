from uuid import uuid4
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from enum import StrEnum, Flag, auto
from collections.abc import Iterable
from abc import ABC, abstractmethod

from aloedav.model.m00_constant import RecurrenceFrequency, AlarmAction, Classification
from aloedav.model.m00_constant import PhoneType, AddressType
from aloedav.model.m01_base import Item, CalendarItem

class CollectionType(StrEnum):
    ADDRESSBOOK="addressbook"
    CALENDAR="calendar"

class ComponentSet(Flag):
    INVALID=0
    VEVENT=auto()
    VJOURNAL=auto()
    VTODO=auto()
    VCONTACT=auto()

class Collection(BaseModel, ABC):
    collection_type: CollectionType
    uid: str
    component_set: ComponentSet
    displayname: str
    description: str
    ctag: str = None
    synctoken: str = None
    items: dict[str, Item] = {}

    @abstractmethod
    def refresh_sync_token(self)-> str|None:
        """
        refresh_sync_token

        returns:
        - current sync token
        """
        pass

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def get_item(self, filename:str)->Item:
        """
        get_item

        returns item
        """
        pass

    @abstractmethod
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

    @abstractmethod
    def insert_item(self, item: Item) -> tuple[str,str]:
        """
        insert_item

        returns tuple[str,str] with [filename, etag]
        """
        pass

    @abstractmethod
    def list_items(self) ->  Iterable[Item]:
        """
        list_items

        returns items
        """
        pass