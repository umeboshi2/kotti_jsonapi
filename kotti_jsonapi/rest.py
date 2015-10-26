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
from kotti.resources import Image
from kotti.util import _
from kotti.util import title_to_name


from kotti.views.edit.actions import NodeActions
from kotti.views.users import UsersManage
from kotti.views.users import principal_schema, user_schema, group_schema

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

from kotti_jsonapi.serializers import relational_metadata

bools = dict(true=True, false=False)

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

@restify(Image)
def file_schema_factory(context, request):
    from kotti.views.edit.content import FileSchema
    return FileSchema(None)


ACCEPT = 'application/vnd.api+json'

def get_messages(request):
    session = request.session
    return dict(info=session.pop_flash('info'),
                success=session.pop_flash('success'),
                error=session.pop_flash('error'),
                warning=session.pop_flash('warning'),
                default=session.pop_flash(''))    

class BaseRestView(object):
    """ A generic @@json view for any and all contexts.

    Its response depends on the HTTP verb used. For ex:
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def _get_messages(self):
        return get_messages(self.request)
    


@view_defaults(name='json', accept=ACCEPT, renderer="kotti_jsonp",
               http_cache=0)
class RestView(BaseRestView):
    """ A generic @@json view for any and all contexts.

    Its response depends on the HTTP verb used. For ex:
    """
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
    
    default_view = colander.SchemaNode(
        colander.String(),
        title=_(u'Default view'),
    )

    in_navigation = colander.SchemaNode(
        #colander.Bool(),
        colander.String(),
        title=_(u'In navigation'),
    )
    path = colander.SchemaNode(
        colander.String(),
        title=_(u'Path'),
    )
    tags = colander.SchemaNode(
        colander.String(),
        title=_(u'Tags'),
    )
    #owner = colander.SchemaNode(
    #    colander.String(),
    #    title=_(u'Owner'),
    #)
    #language = colander.SchemaNode(
    #    colander.String(),
    #    title=_(u'Language'),
    #)


@view_defaults(permission='edit', http_cache=0, renderer='json')
class JSONNodeActions(NodeActions):
    @view_config(name='copyjson')
    def copy_node(self):
        super(JSONNodeActions, self).copy_node()
        return super(JSONNodeActions, self).back()

    @view_config(name='up-json')
    def up(self):
        response = super(JSONNodeActions, self).up()
        meta = dict(messages=get_messages(self.request))
        return dict(result=response, meta=meta)
    
    @view_config(name='down-json')
    def down(self):
        response = super(JSONNodeActions, self).down()
        meta = dict(messages=get_messages(self.request))
        return dict(result=response, meta=meta)
        
    
    def _selected_children(self, add_context=True):
        postdata = self.request.json
        #import pdb ; pdb.set_trace()
        return [int(c) for c in postdata['children']]


@view_config(name="setup-users-json", permission="admin",
             root_only=True, renderer="kotti_jsonp")
class JSONUsersManage(UsersManage):
    def __call__(self):
        data = super(JSONUsersManage, self).__call__()
        data['available_roles'] = [dict(name=r.name, title=r.title)
                                   for r in data['available_roles']]
        parsed_entries = list()
        for principal, groups in data['entries']:
        #for ptuple in data['entries']:
            #@import pdb ; pdb.set_trace()
            pdata = dict(name=principal.name,
                         title=principal.title,
                         avatar_url=data['api'].avatar_url(principal))
            parsed_entries.append(dict(principal=pdata,groups=groups))
        data['entries'] = parsed_entries
        del data['api']
        messages = get_messages(self.request)
        meta = dict(messages=messages)
        return dict(data=data, meta=meta)
    
@view_defaults(name='contents-json', accept=ACCEPT, renderer="kotti_jsonp",
               http_cache=0)
class NodeContents(BaseRestView):
    @view_config(request_method='GET', permission='view')
    def get(self):
        #return self.context
        obj = self.context
        children = list()
        index = 0
        for child in obj.children_with_permission(self.request):
            #cdata = render('kotti_jsonp', child, request=self.request)
            #import pdb ; pdb.set_trace()
            cdata = serialize(child, self.request, include_messages=False)
            cdata['meta']['position'] = index
            index += 1
            #print "CDATA", cdata
            #import pdb ; pdb.set_trace()
            #import cPickle as Pickle
            #filename = "child-%d.pickle" % child.id
            #with file(filename, 'w') as outfile:
            #    Pickle.dump(cdata, outfile)
            #children.append(json.loads(cdata))
            children.append(cdata)
        messages = get_messages(self.request)
        meta = dict(messages=messages)
        return dict(data=children, meta=meta)
    



def serialize(obj, request, name=u'default', relmeta=True,
              include_messages=True):
    """ Serialize a Kotti content item.

    The response JSON conforms with JSONAPI standard.

    TODO: implement JSONAPI filtering and pagination.
    """
    data = get_schema(obj, request, name).serialize(obj.__dict__)
    # FIXME
    data['oid'] = obj.id

    # FIXME kotti_jsonp renderer takes care of this
    for key in ['tags', 'file']:
        if key in data and data[key] is colander.null:
            data[key] = None


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
    # FIXME in_navigation is serialized as string instead of bool
    meta['in_navigation'] = bools[meta['in_navigation'].lower()]
    if include_messages:
        meta['messages'] = get_messages(request)
    if relmeta:
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
jsonp.add_adapter(datetime.datetime, lambda obj, req: obj.isoformat())
jsonp.add_adapter(datetime.time, lambda obj, req: str(obj))

contents_jsonp = JSONP(param_name='callback')


def includeme(config):
    config.add_renderer('kotti_jsonp', jsonp)
    config.scan(__name__)
