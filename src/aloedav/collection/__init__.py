from uuid import uuid4
from typing import Optional
from pydantic import BaseModel
from enum import StrEnum, Flag, auto
from abc import ABC, abstractmethod

class CollectionType(StrEnum):
    ADDRESSBOOK="addressbook"
    CALENDAR="calendar"

class ComponentSet(Flag):
    INVALID=0
    VEVENT=auto()
    VJOURNAL=auto()
    VTODO=auto()
    VCONTACT=auto()

class Item(BaseModel):
    uid: str
    file_ext: str
    version: str
    extended_attributes: Optional[dict[str, str]] = {}
    categories: Optional[list[str]] = []
    etag: Optional[str] = None
    raw_contents: Optional[str] = None

    def update(self, update:"Item"):
        self.etag = str(uuid4()) 
        pass

    def filename(self):
        return f"{self.uid}.{self.file_ext}"

class Collection(BaseModel, ABC):
    collection_type: CollectionType
    uid: str
    component_set: ComponentSet
    displayname: str
    description: str
    
    items: list[Item]

    @abstractmethod
    def delete_item(self, filename:str, etag=None)->bool:
        pass

    @abstractmethod
    def get_item(self, filename:str)->Item:
        pass

    @abstractmethod
    def update_item(self, filename:str, item: Item, etag:str=None) -> bool:
        pass

    @abstractmethod
    def insert_item(self, item: Item) -> bool:
        pass
