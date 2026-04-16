from django import template
import json as _json

register = template.Library()

@register.filter
def index(lst, i):
    try:
        return lst[i]
    except (IndexError, KeyError):
        return ''

@register.filter
def safe_json(value):
    return _json.dumps(value, ensure_ascii=False)
