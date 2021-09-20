import json

from django import template

register = template.Library()


@register.filter
def pretty_json_string(value):
    return json.dumps(json.loads(value), indent=2, sort_keys=True)
