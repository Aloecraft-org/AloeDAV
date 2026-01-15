import requests
import xmltodict
from os import path
from logging import info, error
from pydantic import BaseModel, Field

from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.collection import CollectionType, ComponentSet
from aloedav.model.m00_constant import NS, NS_MAP, CalendarComponents
from aloedav.model.m01_base import Item

listify_dict = lambda d: [d] if isinstance(d,dict) else d

get_multistatus_responses = lambda d: listify_dict(d.get('multistatus',{}).get('response',[]))
get_ok_propfind = lambda response: next((p for p in response.get('propstat', []) if p.get('status', '').endswith('200 OK')), {}).get('prop', {})
get_collection_type = lambda prop: CollectionType.CALENDAR if CollectionType.CALENDAR in prop.get('resourcetype').keys() \
    else CollectionType.ADDRESSBOOK if CollectionType.ADDRESSBOOK in prop.get('resourcetype').keys() \
    else None

get_ctag = lambda prop: prop.get("getctag","")
get_contentcount = lambda prop: prop.get("getcontentcount","")
get_synctoken = lambda prop: prop.get("sync-token","")

get_href = lambda response: response.get('href','').strip("/")
get_collection_user = lambda response: get_href(response).split("/")[0] if len(get_href(response).split("/")) else ''
get_collection_id = lambda response: get_href(response).split("/")[1] if len(get_href(response).split("/")) == 2 else ''


def get_component_set(prop)->ComponentSet:
    component_set = ComponentSet.INVALID
    collection_type = get_collection_type(prop)
    if CollectionType.ADDRESSBOOK == collection_type:
        component_set = ComponentSet.VCONTACT
    elif CollectionType.CALENDAR == collection_type:
        comp_dict_list = listify_dict(prop.get('supported-calendar-component-set',{}).get('comp',[]))
        components = [comp_dict.get('@name') for comp_dict in comp_dict_list if '@name' in comp_dict]
        if 'VEVENT' in components:
            component_set |= ComponentSet.VEVENT
        if 'VJOURNAL' in components:
            component_set |= ComponentSet.VJOURNAL
        if 'VTODO' in components:
            component_set |= ComponentSet.VTODO
    return component_set

def get_description(prop)->str:
    description = ""
    collection_type = get_collection_type(prop)
    if CollectionType.ADDRESSBOOK == collection_type:
        description = prop.get('addressbook-description','')
    elif CollectionType.CALENDAR == collection_type:
        description = prop.get('calendar-description','')
    return description
