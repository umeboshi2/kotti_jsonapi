""" JSON Encoders, serializers, REST views and miscellaneous utilities

The main focus of this module are the REST views. You can trigger them by making
a request with the ACCEPT value of 'application/vnd.api+json' to any Content
subclass. The HTTP verb used in the request determines the action that is taken.

When making requests and publishing objects, we try to follow the JSONAPI
format.

To serialize objects to JSON we reuse Colander schemas.  All
``kotti.resources.Content`` derivates will be automatically serialized, but
they'll only include the fields in ``ContentSchema``. For custom content types,
you should write a serializer such as this:

    from kotti.views.edit.content import DocumentSchema

    @restify(Document)
    def document_schema_factory(context, request):
        from kotti.views.edit.content import DocumentSchema
        return DocumentSchema()

This will also register a content factory for types with name 'Document'.

When deserializing (extracting values from request) we reuse the Colander
schemas to validate those values. Then, these values will be applied to the
context, in POST and PATCH requests. The REST views also handle GET, PUT and
DELETE.

TODO: handle exceptions in the REST view. Any exception should be sent as JSON
response
TODO: handle permissions/security
"""

from kotti.resources import Content, Document, File #, IImage
from kotti.util import _
from kotti.util import title_to_name
from kotti.util import LinkParent, LinkRenderer

from kotti.views.util import TemplateAPI
from kotti.views.edit.actions import workflow as get_workflow
from kotti.views.edit.actions import actions as get_actions
from kotti.views.edit.actions import \
    content_type_factories as get_content_type_factories

from kotti.views.edit.default_views import DefaultViewSelection
from pyramid.httpexceptions import HTTPCreated
from pyramid.httpexceptions import HTTPForbidden
from pyramid.httpexceptions import HTTPNoContent
from pyramid.renderers import JSONP, render
from pyramid.view import view_config, view_defaults
from zope.interface import Interface
import colander
import datetime
import decimal
import json
import venusian


class ISchemaFactory(Interface):
    """ A factory for colander schemas.
    """

    def __call__(context, request):
        """ Returns a colander schema instance """


class IContentFactory(Interface):
    """ A factory for content factories. Can be a class, ex: Document
    """

    def __call__(context, request):
        """ Returns a factory that can construct a new object """


def _schema_factory_name(context=None, type_name=None, name=u'default'):
    """ Returns a named factory name based on either context or type named
    """

    if not any(map(lambda x: x is not None, [context, type_name])):
        raise Exception("Provide a context or a type name")

    type_name = (context is not None) and context.type_info.name or type_name

    return u"{0}/{1}".format(type_name, name)


def restify(klass, name=u'default'):
    """ A decorator to be used to mark a function as a content schema factory.

    The decorated function should return a colander schema instance.

    It will also register the context klass as a factory for that content.
    """

    name = _schema_factory_name(context=klass, name=name)

    def wrapper(wrapped):
        def callback(context, funcname, ob):
            config = context.config.with_package(info.module)
            config.registry.registerUtility(wrapped, ISchemaFactory, name=name)
            config.registry.registerUtility(klass, IContentFactory,
                                            name=klass.type_info.name)

        info = venusian.attach(wrapped, callback, category='pyramid')
        return wrapped

    return wrapper


@restify(Content)
def content_schema_factory(context, request):
    from kotti.views.edit.content import ContentSchema
    return ContentSchema()


@restify(Document)
def document_schema_factory(context, request):
    from kotti.views.edit.content import DocumentSchema
    return DocumentSchema()


@restify(File)
def file_schema_factory(context, request):
    from kotti.views.edit.content import FileSchema
    return FileSchema(None)


ACCEPT = 'application/vnd.api+json'

@view_defaults(name='json', accept=ACCEPT, renderer="kotti_jsonp")
class RestView(object):
    """ A generic @@json view for any and all contexts.

    Its response depends on the HTTP verb used. For ex:
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    @view_config(request_method='GET', permission='view')
    def get(self):
        return self.context

    @view_config(request_method='POST', permission='edit')
    def post(self):
        data = self.request.json_body['data']

        assert data['id'] == self.context.name
        assert data['type'] == self.context.type_info.name

        schema = get_schema(self.context, self.request)
        validated = schema.deserialize(data['attributes'])

        for k, v in validated.items():
            setattr(self.context, k, v)

        return self.context

    @view_config(request_method='PATCH', permission='edit')
    def patch(self):
        data = self.request.json_body['data']

        assert data['id'] == self.context.name
        assert data['type'] == self.context.type_info.name

        schema = get_schema(self.context, self.request)
        validated = schema.deserialize(data['attributes'])
        attrs = dict((k, v) for k, v in validated.items()
                     if k in data['attributes'])
        for k, v in attrs.items():
            setattr(self.context, k, v)

        return self.context

    @view_config(request_method='PUT')
    def put(self):
        # we never accept id, it doesn't conform to jsonapi format
        data = self.request.json_body['data']

        klass = get_content_factory(self.request, data['type'])

        add_permission = klass.type_info.add_permission
        if not self.request.has_permission(add_permission, self.context):
            raise HTTPForbidden()

        schema_name = _schema_factory_name(type_name=data['type'])
        schema_factory = self.request.registry.getUtility(ISchemaFactory,
                                                          name=schema_name)
        schema = schema_factory(None, self.request)
        validated = schema.deserialize(data['attributes'])

        name = title_to_name(validated['title'], blacklist=self.context.keys())
        new_item = self.context[name] = klass(**validated)

        response = HTTPCreated()
        response.body = render('kotti_jsonp', new_item, self.request)
        return response

    @view_config(request_method='DELETE', permission='delete')
    def delete(self):
        # data = self.request.json_body['data']

        parent = self.context.__parent__
        del parent[self.context.__name__]
        return HTTPNoContent()


def get_schema(obj, request, name=u'default'):
    factory_name = _schema_factory_name(context=obj, name=name)
    schema_factory = request.registry.getUtility(ISchemaFactory,
                                                 name=factory_name)
    return schema_factory(obj, request)


def get_content_factory(request, name):
    return request.registry.getUtility(IContentFactory, name=name)


# def filter_schema(schema, allowed_fields):
#     """ Filters a schema to include only allowed fields
#     """
#
#     cloned = schema.__class__(self.typ)
#     cloned.__dict__.update(schema.__dict__)
#     cloned.children = [node.clone() for node in self.children
#                        if node.name in allowed_fields]
#     return cloned
#

class MetadataSchema(colander.MappingSchema):
    """ Schema that exposes some metadata information about a content
    """

    modification_date = colander.SchemaNode(
        colander.Date(),
        title=_(u'Modification Date'),
    )

    creation_date = colander.SchemaNode(
        colander.Date(),
        title=_(u'Modification Date'),
    )

    state = colander.SchemaNode(
        colander.String(),
        title=_(u'State'),
    )
    state = colander.SchemaNode(
        colander.String(),
        title=_(u'State'),
    )

    default_view = colander.SchemaNode(
        colander.String(),
        title=_(u'Default view'),
    )

    in_navigation = colander.SchemaNode(
        colander.String(),
        title=_(u'In navigation'),
    )



def serialize_user(context, request, api=None):
    if api is None:
        api = TemplateAPI(context, request)
    udata = None
    user = request.user
    if user is not None:
        udata = dict()
        for key in ['id', 'email', 'groups', 'name', 'title']:
            udata[key] = getattr(user, key)
        for dt in ['creation_date', 'last_login_date']:
            value = getattr(user, dt)
            if value is not None:
                value = value.isoformat()
            udata[dt] = value
        udata['avatar_prefix'] = api.avatar_url(user=request.user, size='')
        udata['prefs_url'] = api.url(api.root, '@@prefs')
    return udata


def get_link_info(link, context, request):
    link_data = dict()
    for key in ['name', 'path', 'target', 'template',
                'title']:
        if hasattr(link, key):
            link_data[key] = getattr(link, key)
    for key in ['selected', 'url', 'visible']:
        if hasattr(link, key):
            link_data[key] = getattr(link, key)(context, request)
    for key in ['permitted']:
        if hasattr(link, key):
            link_data[key] = bool(getattr(link, key)(context, request).boolval)
    for key in ['predicate']:
        if hasattr(link, key):
            value = getattr(link, key)
            if value is not None:
                value = value(context, request)
            link_data[key] = value
    return link_data

def handle_link_parent(link, context, request):
    children = link.get_visible_children(context, request)
    action_links = list()
    for link in children:
        if type(link) is not LinkRenderer:
            action_links.append(get_link_info(link, context, request))
        else:
            continue
    return action_links

def relational_metadata(obj, request):
    # some of this is just to mimick templates
    relmeta = dict()
    api = TemplateAPI(obj, request)
    
    navitems = list()
    for item in api.list_children(api.navigation_root):
        if item.in_navigation:
            idata = dict(inside=api.inside(obj, item),
                        url=api.url(item),
                        description=item.description,
                        title=item.title)
            navitems.append(idata)
    relmeta['navitems'] = navitems

    # type info
    type_info = dict()
    for attr in ['selectable_default_views', 'title',
                 'addable_to', 'add_permission']:
        type_info[attr] = getattr(obj.type_info, attr)
    relmeta['type_info'] = type_info

    # permissions
    has_permission = dict()
    for key in ['add', 'edit', 'state_change']:
        has_permission[key] = bool(api.has_permission(key).boolval)
    has_permission['admin'] = bool(api.has_permission('admin', api.root).boolval)
    relmeta['has_permission'] = has_permission
        

    # for top navbar
    relmeta['application_url'] = request.application_url
    relmeta['site_title'] = api.site_title
    relmeta['root_url'] = api.url(api.root)
    
    # for edit bar
    wf = get_workflow(obj, request)
    if wf['current_state'] is not None:
        if 'callback' in wf['current_state'].get('data', dict()):
            del wf['current_state']['data']['callback']
        for state in wf['states']:
            sdata = wf['states'][state].get('data', dict())
            if 'callback' in sdata:
                del sdata['callback']
    relmeta['workflow'] = wf
    relmeta['request_url'] = request.url
    relmeta['api_url'] = api.url()
    
    edit_links = list()
    link_parent = None
    for link in api.edit_links:
        if type(link) is not LinkParent:
            edit_links.append(get_link_info(link, obj, request))
        else:
            link_parent = handle_link_parent(link, obj, request)
    relmeta['edit_links'] =  edit_links
    relmeta['link_parent'] = link_parent
    
    dfs = DefaultViewSelection(obj, request)
    key = 'selectable_default_views'
    relmeta[key] = dfs.default_view_selector()[key]
    del dfs
    del key
    
    
    # add-dropdown
    factories = get_content_type_factories(obj, request)['factories']
    flist = list()
    for f in factories:
        flist.append(dict(
            url=api.url(obj, f.type_info.add_view),
            title=f.type_info.title,
            ))
    relmeta['content_type_factories'] = flist
    relmeta['upload_url'] = api.url(obj, 'upload')

    # site_setup_linke
    site_setup_links = list()
    for link in api.site_setup_links:
        site_setup_links.append(get_link_info(link, obj, request))
    # FIXME this fixes a problem where a plugin seems to define an
    # extra settings link
    site_setup_urls = list()
    setup_links = list()
    for link in site_setup_links:
        if link['url'] not in site_setup_urls:
            site_setup_urls.append(link['url'])
            setup_links.append(link)
    relmeta['site_setup_links'] = setup_links

    
    relmeta['navigate_url'] = api.url(obj, '@@navigate')
    relmeta['logout_url'] = api.url(api.root, '@@logout',
                                       query=dict(came_from=request.url))

    # page content
    relmeta['has_location_context'] = api.is_location(obj)
    relmeta['view_needed'] = api.view_needed

    breadcrumbs = list()
    for bc in api.breadcrumbs:
        breadcrumbs.append(dict(id=bc.id,
                                name=bc.name,
                                description=bc.description,
                                url=api.url(bc),
                                title=bc.title))
    relmeta['breadcrumbs'] = breadcrumbs
    
    # FIXME figure out what to do about page_slots
    #relmeta['page_slots'] = api.slots
    relmeta['paths'] = {
        'this_path': request.resource_path(obj),
        'child_paths': [request.resource_path(child)
                        for child in obj.children_with_permission(request)],
        'childnames': [child.__name__
                       for child in obj.children_with_permission(request)],
    }
    
    relmeta['current_user'] = serialize_user(obj, request, api=api)
    
    #import pdb ; pdb.set_trace()
    return relmeta

def serialize(obj, request, name=u'default'):
    """ Serialize a Kotti content item.

    The response JSON conforms with JSONAPI standard.

    TODO: implement JSONAPI filtering and pagination.
    """
    data = get_schema(obj, request, name).serialize(obj.__dict__)

    res = {}
    res['type'] = obj.type_info.name
    res['id'] = obj.__name__
    res['attributes'] = data
    res['links'] = {
        'self': request.resource_url(obj),
        'children': [request.resource_url(child)
                     for child in obj.children_with_permission(request)]
    }
    meta = MetadataSchema().serialize(obj.__dict__)

    # make data.relationships.meta object
    rel = dict()
    relmeta = dict()
    rel['meta'] = relational_metadata(obj, request)
    res['relationships'] = rel
    
    
    return dict(data=res, meta=meta)


jsonp = JSONP(param_name='callback')
jsonp.add_adapter(Content, serialize)
jsonp.add_adapter(colander._null, lambda obj, req: None)
jsonp.add_adapter(datetime.date, lambda obj, req: str(obj))
jsonp.add_adapter(datetime.datetime, lambda obj, req: str(obj))
jsonp.add_adapter(datetime.time, lambda obj, req: str(obj))


def includeme(config):
    config.add_renderer('kotti_jsonp', jsonp)
    config.scan(__name__)
