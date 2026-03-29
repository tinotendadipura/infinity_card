from django import template

register = template.Library()

@register.filter
def make_range(value, start=0):
    """Returns a range from start to value (exclusive)"""
    return range(start, value)

@register.filter
def make_range_range(start, end):
    """Returns a range from start to end (exclusive)"""
    return range(start, end)
