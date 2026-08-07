from pydantic import BaseModel
from aloedav.collection import CollectionType, ComponentSet
from aloedav.client_util import listify_dict
from aloedav.client_util import get_multistatus_responses
from aloedav.client_util import get_ok_propfind
from aloedav.client_util import get_collection_type
from aloedav.client_util import get_ctag
from aloedav.client_util import get_contentcount
from aloedav.client_util import get_synctoken
from aloedav.client_util import get_href
from aloedav.client_util import get_collection_user
from aloedav.client_util import get_collection_id
from aloedav.client_util import get_component_set
from aloedav.client_util import get_description

class DAVCollection(BaseModel):
    href:str
    displayname:str
    description:str
    collection_id:str
    user:str
    ctag:str
    synctoken:str
    contentcount:str
    collection_type:CollectionType
    component_set:ComponentSet

    @classmethod
    def from_response(cls,response):
        prop = get_ok_propfind(response)
        return cls(
            href=get_href(response),
            displayname=prop.get('displayname') or '',
            collection_type=get_collection_type(prop),
            component_set=get_component_set(prop),
            description=get_description(prop),
            collection_id=get_collection_id(response),
            user=get_collection_user(response),
            contentcount=get_contentcount(prop),
            ctag=get_ctag(prop),
            synctoken=get_synctoken(prop))

    def __str__(self):
        return f"""
{self.collection_type}: {self.displayname}
====
- href: {self.href}
- component_set: {self.component_set}
- description: {self.description}
- collection_id: {self.collection_id}
- collection_user: {self.user}
- ctag: {self.ctag}
- synctoken: {self.synctoken}
- contentcount: {self.contentcount}
"""