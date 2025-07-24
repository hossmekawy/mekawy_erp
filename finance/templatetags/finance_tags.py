# finance/templatetags/finance_tags.py

from django import template
from django.utils.safestring import mark_safe
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter(name='currency')
def currency(value):
    """
    Formats a number as Egyptian Pound currency.
    Example: 1234.56 -> "١٬٢٣٤٫٥٦ ج.م."
    """
    try:
        value = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return value

    # Format the number with commas and two decimal places
    formatted_value = "{:,.2f}".format(value)
    
    # Replace with Arabic numerals and symbols
    arabic_numerals = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩',
        '.': '٫', ',': '٬'
    }
    
    for en, ar in arabic_numerals.items():
        formatted_value = formatted_value.replace(en, ar)

    return f"{formatted_value} ج.م."

@register.filter(name='neg_currency')
def neg_currency(value):
    """
    Formats a number as currency and wraps negative values in a span with a Bootstrap 'text-danger' class.
    """
    try:
        d_value = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return value
        
    formatted = currency(d_value)
    if d_value < 0:
        # Use Bootstrap's 'text-danger' class for red color
        return mark_safe(f'<span class="text-danger fw-bold">({formatted.replace("-", "")})</span>')
    return formatted
