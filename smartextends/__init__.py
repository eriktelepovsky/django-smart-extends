try:
    from django.template.loader import add_to_builtins
except ImportError:
    from django.template.base import add_to_builtins

add_to_builtins('smartextends.templatetags.smart_extends_tags')