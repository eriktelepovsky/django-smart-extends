import django
from django.template import TemplateSyntaxError, TemplateDoesNotExist
from django.template import Library
from django.conf import settings

from django.template.loader import template_source_loaders, make_origin
from django.template.loader_tags import ExtendsNode
from django.utils.importlib import import_module

register = Library()

# Django 1.2
def find_template(name, dirs=None, skip_template=None):
    from django.template.loader import find_template_loader
    # Calculate template_source_loaders the first time the function is executed
    # because putting this logic in the module-level namespace may cause
    # circular import errors. See Django ticket #1292.
    global template_source_loaders
    if template_source_loaders is None:
        loaders = []
        for loader_name in settings.TEMPLATE_LOADERS:
            loader = find_template_loader(loader_name)
            if loader is not None:
                loaders.append(loader)
        template_source_loaders = tuple(loaders)
    for loader in template_source_loaders:
        try:
            source, display_name = loader(name, dirs)
            if skip_template:
                extends_tags = source.nodelist[0]
                if extends_tags.source[0].name == skip_template:
                    continue
            return (source, make_origin(display_name, loader, name, dirs))
        except TemplateDoesNotExist:
            pass
    raise TemplateDoesNotExist(name)

# Django 1.1
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
    for loader in template_source_loaders:
        try:
            source, display_name = loader(name, dirs)
            if skip_template:
                if display_name == skip_template:
                    continue
            return (source, make_origin(display_name, loader, name, dirs))
        except TemplateDoesNotExist:
            pass
    raise TemplateDoesNotExist, name


class SmartExtendsNode(ExtendsNode):

    def __repr__(self):
        if self.parent_name_expr:
            return "<SmartExtendsNode: extends %s>" % self.parent_name_expr.token
        return '<SmartExtendsNode: extends "%s">' % self.parent_name

    def render(self, context):
        source = getattr(self, 'source', None)
        source = source and source[0]
        if source and source.loadname == self.parent_name:
            if django.VERSION[0] == 1 and django.VERSION[1] <= 1:
                template = find_template_source(self.parent_name, skip_template=source.name)
                self.parent_name = template[1][0].name
            else:
                template = find_template(self.parent_name, skip_template=source.name)
                template_source = template[0]
                extends_tags = template_source.nodelist[0]
                self.parent_name = extends_tags.source[0].name
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
