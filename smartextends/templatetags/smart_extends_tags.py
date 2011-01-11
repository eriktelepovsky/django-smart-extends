# Copyright (c) 2010 by Yaco Sistemas <pmartin@yaco.es>
#
# This software is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

import django
from django.template import TemplateSyntaxError, TemplateDoesNotExist
from django.template import Library
from django.conf import settings
from django.template.loader import get_template_from_string
from django.template.loader import template_source_loaders, make_origin
from django.template.loader_tags import ExtendsNode
from django.utils.importlib import import_module

register = Library()


def get_source(source):
    if getattr(source, '__iter__', None):
        source = source[0]
    return source

def find_template_source(name, dirs=None, skip_template=None):
    # Calculate template_source_loaders the first time the function is executed
    # because putting this logic in the module-level namespace may cause
    # circular import errors. See Django ticket #1292.
    global template_source_loaders
    if template_source_loaders is None:
        loaders = []
        for path in settings.TEMPLATE_LOADERS:
            i = path.rfind('.')
            module, attr = path[:i], path[i+1:]
            try:
                mod = import_module(module)
            except ImportError, e:
                raise ImproperlyConfigured, 'Error importing template source loader %s: "%s"' % (module, e)
            try:
                func = getattr(mod, attr)
            except AttributeError:
                raise ImproperlyConfigured, 'Module "%s" does not define a "%s" callable template source loader' % (module, attr)
            if not func.is_usable:
                import warnings
                warnings.warn("Your TEMPLATE_LOADERS setting includes %r, but your Python installation doesn't support that type of template loading. Consider removing that line from TEMPLATE_LOADERS." % path)
            else:
                loaders.append(func)
        template_source_loaders = tuple(loaders)
    template_candidate = None
    for loader in template_source_loaders:
        try:
            source, display_name = loader(name, dirs)
            if skip_template:
                if display_name == skip_template.name:
                    template_candidate = None
                    continue
                if not template_candidate:
                    template_candidate = (source, make_origin(display_name, loader, name, dirs))
            else:
                return (source, make_origin(display_name, loader, name, dirs))
        except TemplateDoesNotExist:
            pass
    if not template_candidate:
        raise TemplateDoesNotExist, name
    return template_candidate


class SmartExtendsNode(ExtendsNode):

    def __repr__(self):
        if self.parent_name_expr:
            return "<SmartExtendsNode: extends %s>" % self.parent_name_expr.token
        return '<SmartExtendsNode: extends "%s">' % self.parent_name

    def get_source(self):
        source = getattr(self, 'source', None)
        return get_source(source)

    def get_parent(self, context):
        source = self.get_source()
        if self.parent_name_expr:
            self.parent_name = self.parent_name_expr.resolve(context)
        parent = self.parent_name
        if not parent:
            error_msg = "Invalid template name in 'extends' tag: %r." % parent
            if self.parent_name_expr:
                error_msg += " Got this from the '%s' variable." % self.parent_name_expr.token
            raise TemplateSyntaxError, error_msg
        if hasattr(parent, 'render'):
            return parent # parent is a Template object
        try:
            source, origin = find_template_source(parent, self.template_dirs, skip_template=source)
        except TemplateDoesNotExist:
            raise TemplateSyntaxError, "Template %r cannot be extended, because it doesn't exist" % parent
        else:
            return get_template_from_string(source, origin, parent)

    def render(self, context):
        source = self.get_source()
        if source and source.loadname == self.parent_name:
            template = find_template_source(self.parent_name, skip_template=source)
            self.parent_name = template[1].name
        return super(SmartExtendsNode, self).render(context)


def do_smart_extends(parser, token):
    """
    Signal that this template smart_extends a parent template.

    This tag may be used similarly to extends (django tag).
    This tag provides the possibility to extend to yourself without infinite
    recursion. It is possible for use a API function "find_template",
    that skip the invoke template 
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise TemplateSyntaxError("'%s' takes one argument" % bits[0])
    parent_name, parent_name_expr = None, None
    if bits[1][0] in ('"', "'") and bits[1][-1] == bits[1][0]:
        parent_name = bits[1][1:-1]
    else:
        parent_name_expr = parser.compile_filter(bits[1])
    nodelist = parser.parse()
    if nodelist.get_nodes_by_type(SmartExtendsNode):
        raise TemplateSyntaxError("'%s' cannot appear more than once in the same template" % bits[0])
    return SmartExtendsNode(nodelist, parent_name, parent_name_expr)


if getattr(settings, 'OVERWRITE_EXTENDS', False):
    register.tag('extends', do_smart_extends)
register.tag('smart_extends', do_smart_extends)
