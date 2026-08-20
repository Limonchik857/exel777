from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Достаёт значение из dict по ключу (для доступа к атрибутам с '.')."""
    if isinstance(mapping, dict):
        return mapping.get(key, "")
    return ""