from django import template
from decimal import Decimal

register = template.Library()



@register.filter(name='div')
def div(value, arg):
    """Divides the value by the argument."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return None # Return None or 0 if division is not possible
@register.filter(name='multiply')
def multiply(value, arg):
    """Multiplies the value by the argument."""
    try:
        return Decimal(value) * Decimal(arg)
    except (ValueError, TypeError):
        return ''
@register.filter
def status_color(status):
    """Return Bootstrap color class for production order status"""
    color_map = {
        'pending': 'warning',
        'approved': 'info',
        'in_cutting': 'primary',
        'in_assembly': 'primary',
        'in_dyeing': 'primary',
        'in_finishing': 'primary',
        'quality_check': 'secondary',
        'completed': 'success',
        'cancelled': 'danger',
    }
    return color_map.get(status, 'secondary')

@register.filter
def movement_color(movement_type):
    """Return Bootstrap color class for stock movement type"""
    color_map = {
        'in': 'success',
        'out': 'danger',
        'transfer': 'info',
        'adjustment': 'warning',
        'return': 'secondary',
    }
    return color_map.get(movement_type, 'secondary')

@register.filter(name='split')
def split_string(value, arg):
    """
    Splits a string by the given argument.
    Usage: {{ "hello,world"|split:"," }}
    """
    if isinstance(value, str):
        return value.split(arg)
    return []

@register.filter(name='index_of')
def index_of(sequence, item):
    """
    Returns the 1-based index of an item in a sequence.
    Returns 0 if the item is not found.
    """
    try:
        # Add 1 to make it 1-based for easier template logic (e.g., {% if index >= 2 %})
        return sequence.index(item) + 1
    except (ValueError, TypeError):
        # Return 0 if the item is not in the list or if it's not a list
        return 0

@register.filter
def mul(value, arg):
    """
    Multiplies the value with the argument.
    Usage: {{ value|mul:arg }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''