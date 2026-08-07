import requests
import xmltodict
from os import path
from logging import info, error
from pydantic import BaseModel, Field

from aloedav.exceptions import AuthenticationError, ResourceNotFound, PreconditionFailed, WebDAVError, AloeDAVClientError
from aloedav.collection import CollectionType, ComponentSet
from aloedav.model.m00_constant import NS, NS_MAP, CalendarComponents
from aloedav.model.m01_base import Item

listify_dict = lambda d: [d] if isinstance(d,dict) else (d or [])

get_multistatus_responses = lambda d: listify_dict(d.get('multistatus',{}).get('response',[]))
# xmltodict collapses a lone <propstat> to a dict, so it has to be listified
# before iterating -- otherwise iteration yields the element's keys as strings.
get_ok_propfind = lambda response: next((p for p in listify_dict(response.get('propstat', [])) if (p.get('status') or '').endswith('200 OK')), {}).get('prop', {})
# resourcetype is absent on non-collection resources and empty (None) on plain
# collections, so neither case can be dereferenced blindly.
get_resourcetype = lambda prop: prop.get('resourcetype') or {}
get_collection_type = lambda prop: CollectionType.CALENDAR if CollectionType.CALENDAR in get_resourcetype(prop).keys() \
    else CollectionType.ADDRESSBOOK if CollectionType.ADDRESSBOOK in get_resourcetype(prop).keys() \
    else None

get_ctag = lambda prop: prop.get("getctag") or ""
get_contentcount = lambda prop: prop.get("getcontentcount") or ""
get_synctoken = lambda prop: prop.get("sync-token") or ""

get_href = lambda response: (response.get('href') or '').strip("/")
# The collection is the last path segment and its owner the one before it, so
# that servers which mount the DAV tree under a prefix still resolve correctly.
get_href_segments = lambda response: [s for s in get_href(response).split("/") if s]
get_collection_user = lambda response: get_href_segments(response)[-2] if len(get_href_segments(response)) >= 2 else ''
get_collection_id = lambda response: get_href_segments(response)[-1] if get_href_segments(response) else ''


def get_component_set(prop)->ComponentSet:
    component_set = ComponentSet.INVALID
    collection_type = get_collection_type(prop)
    if CollectionType.ADDRESSBOOK == collection_type:
        component_set = ComponentSet.VCONTACT
    elif CollectionType.CALENDAR == collection_type:
        comp_dict_list = listify_dict((prop.get('supported-calendar-component-set') or {}).get('comp'))
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
        description = prop.get('addressbook-description')
    elif CollectionType.CALENDAR == collection_type:
        description = prop.get('calendar-description')
    # An empty <description/> element parses to None rather than a string.
    return description or ""
