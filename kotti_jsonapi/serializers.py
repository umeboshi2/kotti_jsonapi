import os

from kotti.util import _
from kotti.util import LinkParent, LinkRenderer

from kotti.views.util import TemplateAPI
from kotti.views.edit.actions import workflow as get_workflow
from kotti.views.edit.actions import actions as get_actions
from kotti.views.edit.actions import \
    content_type_factories as get_content_type_factories
from kotti.views.edit.actions import contents_buttons as get_contents_buttons


from kotti.views.edit.default_views import DefaultViewSelection
from pyramid.interfaces import ILocation




#import json


class JSONTemplateAPI(TemplateAPI):
    def path(self, context=None, *elements, **kwargs):
        """
        URL construction helper. Just a convenience wrapper for
        :func:`pyramid.request.resource_url` with the same signature.  If
        ``context`` is ``None`` the current context is passed to
        ``resource_url``.
        """

        if context is None:
            context = self.context
        if not ILocation.providedBy(context):
            return self.request.path
        return self.request.resource_path(context, *elements, **kwargs)



def serialize_user(context, request, api=None):
    if api is None:
        api = JSONTemplateAPI(context, request)
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

def get_button_info(button_link, context, request):
    link_data = get_link_info(button_link, context, request)
    link_data['css_classes'] = button_link.css_class.split()
    link_data['no_children'] = button_link.no_children
    link_data['template'] = button_link.template
    return link_data


def handle_link_parent(link, context, request, api):
    children = link.get_visible_children(context, request)
    action_links = list()
    for link in children:
        if type(link) is not LinkRenderer:
            link_info = get_link_info(link, context, request)
            path = api.path(context, request)
            resource, command = os.path.split(path)
            link_info['resource'] = resource
            link_info['command'] = command
            action_links.append(link_info)
        else:
            continue
    return action_links

def relational_metadata(obj, request, get_user=True,
                        get_type_info=True,
                        get_permissions=True,
                        get_extra_info=True):
    # some of this is just to mimick templates
    relmeta = dict()
    api = JSONTemplateAPI(obj, request)
    if get_user:
        relmeta['current_user'] = serialize_user(obj, request, api=api)

    if get_type_info:
        # type info
        type_info = dict()
        for attr in ['selectable_default_views', 'title', 'name',
                     'addable_to', 'add_permission']:
            type_info[attr] = getattr(obj.type_info, attr)
        if type_info['name'] == 'Image':
            for span in ['span1', 'span4']:
                key = 'image_%s_url' % span
                type_info[key] = request.resource_url(obj, 'image', span)
        relmeta['type_info'] = type_info

    if get_permissions:
        # permissions
        has_permission = dict()
        for key in ['add', 'edit', 'state_change']:
            has_permission[key] = bool(api.has_permission(key).boolval)
        has_permission['admin'] = bool(
            api.has_permission('admin', api.root).boolval)
        relmeta['has_permission'] = has_permission
        

    if not get_extra_info:
        return relmeta
    
    # for top navbar
    navitems = list()
    for item in api.list_children(api.navigation_root):
        if item.in_navigation:
            idata = dict(inside=api.inside(obj, item),
                         url=api.url(item),
                         path=api.path(item),
                         description=item.description,
                         title=item.title)
            navitems.append(idata)
    relmeta['navitems'] = navitems



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
            link_info = get_link_info(link, obj, request)
            path = api.path(obj, request)
            resource, command = os.path.split(path)
            link_info['resource'] = resource
            link_info['command'] = command
            edit_links.append(link_info)
        else:
            link_parent = handle_link_parent(link, obj, request, api)
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
        path = api.path(obj, f.type_info.add_view)
        flist.append(dict(
            url=api.url(obj, f.type_info.add_view),
            resource=os.path.dirname(path),
            command=os.path.basename(path),
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
                                path=api.path(bc),
                                title=bc.title))
    relmeta['breadcrumbs'] = breadcrumbs

    lineage = list()
    for node in api.lineage:
        lineage.append(dict(id=node.id,
                            name=node.name,
                            description=node.description,
                            url=api.url(node),
                            path=api.path(node),
                            title=node.title))
    relmeta['lineage'] = lineage
    # FIXME - do this client side
    #http://stackoverflow.com/questions/3705670/best-way-to-create-a-reversed-list-in-python
    #relmeta['lineage_reversed'] = lineage[::-1]
    
    # FIXME figure out what to do about page_slots
    #relmeta['page_slots'] = api.slots
    relmeta['paths'] = {
        'this_path': request.resource_path(obj),
        'child_paths': [request.resource_path(child)
                        for child in obj.children_with_permission(request)],
        'childnames': [child.__name__
                       for child in obj.children_with_permission(request)],
    }
    
    

    # contents_buttons
    cbuttons = [get_button_info(b, obj, request)
                for b in get_contents_buttons(obj, request)]
    relmeta['contents_buttons'] = cbuttons

    return relmeta

