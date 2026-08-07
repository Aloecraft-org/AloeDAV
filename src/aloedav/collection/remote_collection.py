from enum import StrEnum
from pydantic import BaseModel, Field, ConfigDict
from collections.abc import Iterable
from uuid import uuid4

from aloedav.exceptions import PreconditionFailed, WebDAVError, ResourceNotFound, AloeDAVClientError
from aloedav.collection import Collection, ComponentSet, Item, CollectionType
from aloedav.model.m00_constant import CalendarComponents
from aloedav.client import AloeDAVClient

class RemoteCollection(Collection):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client:AloeDAVClient = Field(exclude=True)
    # Server-assigned metadata: absent until the collection has been fetched.
    href:str = ""
    ctag:str = ""
    synctoken:str = ""
    contentcount:str = ""

    @classmethod
    def get_or_create(cls, client:AloeDAVClient, displayname:str, description:str, collection_id:str, collection_type:CollectionType, component_set: ComponentSet=None):
        """
        Creates the collection on the server if it does not exist, then returns
        it populated with the server's metadata.

        displayname and description are ignored if the collection already exists
        """
        match collection_type:
            case CollectionType.ADDRESSBOOK:
                return cls.get_or_create_addressbook(client, displayname, description, collection_id)
            case CollectionType.CALENDAR:
                components = CalendarComponents.INVALID
                if component_set:
                    if ComponentSet.VEVENT in component_set:
                        components |= CalendarComponents.VEVENT
                    if ComponentSet.VJOURNAL in component_set:
                        components |= CalendarComponents.VJOURNAL
                    if ComponentSet.VTODO in component_set:
                        components |= CalendarComponents.VTODO
                else:
                    components = CalendarComponents.VEVENT | CalendarComponents.VTODO | CalendarComponents.VJOURNAL
                return cls.get_or_create_calendar(client, displayname, description, collection_id, components)
            case _:
                raise AloeDAVClientError(f"Cannot create collection of type: {collection_type}")

    @classmethod
    def get_or_create_addressbook(cls, client:AloeDAVClient, display_name:str, description:str, addressbook_id:str):
        """
        displayname and description will be ignored if collection already exists
        """
        client.create_addressbook(display_name, description, addressbook_id)
        dav_collection = client.fetch_collection(addressbook_id)
        return cls(client = client,
            uid=addressbook_id,
            href=dav_collection.href,
            ctag=dav_collection.ctag,
            synctoken=dav_collection.synctoken,
            contentcount=dav_collection.contentcount,
            displayname=dav_collection.displayname, 
            description=dav_collection.description, 
            component_set=dav_collection.component_set, 
            collection_type = dav_collection.collection_type)

    @classmethod
    def get_or_create_calendar(cls, client:AloeDAVClient, display_name:str, description:str, calendar_id:str, components:CalendarComponents=CalendarComponents.VEVENT|CalendarComponents.VTODO|CalendarComponents.VJOURNAL):
        """
        displayname and description will be ignored if collection already exists
        """
        client.create_calendar(display_name, description, calendar_id, components)
        dav_collection = client.fetch_collection(calendar_id)
        
        return cls(client = client,
            uid=calendar_id,
            href=dav_collection.href,
            ctag=dav_collection.ctag,
            synctoken=dav_collection.synctoken,
            contentcount=dav_collection.contentcount,
            displayname=dav_collection.displayname, 
            description=dav_collection.description, 
            component_set=dav_collection.component_set, 
            collection_type = dav_collection.collection_type)

    def _refresh(self):
        dav_collection = self.client.fetch_collection(self.uid)
        self.href = dav_collection.href
        self.ctag = dav_collection.ctag
        self.synctoken = dav_collection.synctoken
        self.contentcount = dav_collection.contentcount
        self.displayname = dav_collection.displayname
        self.description = dav_collection.description
        self.component_set = dav_collection.component_set
        self.collection_type = dav_collection.collection_type

    def refresh_sync_token(self)-> str|None:
        """
        refresh_sync_token

        returns:
        - current sync token
        """
        self._refresh()
        return self.synctoken

    def sync_collection(self, sync_token: str) -> dict:
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
        return self.client.sync_collection(self.uid, sync_token)

    def delete_item(self, filename:str, etag=None)->bool:
        """
        delete_item
        
        raises:
        - WebDAVError if filename not found
        - PreconditionFailed if ETag mismatch

        returns:
        - True if successful
        """
        return self.client.delete_object(self.uid, filename, etag)


    def get_item(self, filename:str)->Item:
        """
        get_item

        returns item
        """
        # fetch_object returns every component in the resource; a collection
        # entry addressed by filename holds exactly one for our purposes.
        items = self.client.fetch_object(self.uid, filename)
        if not items:
            raise ResourceNotFound(f"No object found in {self.uid}/{filename}")
        return items[0]


    def update_item(self, filename:str, item: Item, etag:str=None) -> str:
        """
        update_item

        raises:
        - WebDAVError if filename not found
        - PreconditionFailed if ETag mismatch

        returns: 
        - new etag
        """
        webdav_obj = self.client.upsert_object(self.uid, item, etag)
        return webdav_obj.etag

    def insert_item(self, item: Item) -> tuple[str,str]:
        """
        insert_item

        returns tuple[str,str] with [filename, etag]
        """
        webdav_obj = self.client.upsert_object(self.uid, item)
        return webdav_obj.filename(), webdav_obj.etag

    def list_items(self) ->  Iterable[Item]:
        """
        list_items

        returns items
        """
        if self.collection_type == CollectionType.ADDRESSBOOK:
            return self.client.list_addressbook_objects(self.uid)
        elif self.collection_type == CollectionType.CALENDAR:
            return self.client.list_calendar_objects(self.uid)
        else:
            raise AloeDAVClientError(f"Cannot list items for collection type: {self.collection_type}")
        

    def delete_collection(self)->bool:
        """
        delete_collection
        """
        return self.client.delete_collection(self.uid)