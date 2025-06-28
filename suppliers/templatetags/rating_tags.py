from django import template
from django.utils.safestring import mark_safe
import math

register = template.Library()

@register.simple_tag
def star_rating(rating, max_stars=5, show_number=True):
    """Display star rating"""
    if not rating:
        rating = 0
    
    full_stars = int(rating)
    half_star = 1 if rating - full_stars >= 0.5 else 0
    empty_stars = max_stars - full_stars - half_star
    
    stars_html = []
    
    # Full stars
    for i in range(full_stars):
        stars_html.append('<i class="fas fa-star text-warning"></i>')
    
    # Half star
    if half_star:
        stars_html.append('<i class="fas fa-star-half-alt text-warning"></i>')
    
    # Empty stars
    for i in range(empty_stars):
        stars_html.append('<i class="far fa-star text-muted"></i>')
    
    stars_str = ''.join(stars_html)
    
    if show_number:
        return mark_safe(f'{stars_str} <span class="ms-1 text-muted">({rating:.1f})</span>')
    else:
        return mark_safe(stars_str)

@register.simple_tag
def rating_color(rating):
    """Get color class for rating"""
    if not rating:
        return 'secondary'
    
    if rating >= 4.5:
        return 'success'
    elif rating >= 3.5:
        return 'primary'
    elif rating >= 2.5:
        return 'warning'
    else:
        return 'danger'

@register.simple_tag
def rating_text(rating):
    """Get text description for rating"""
    if not rating:
        return 'غير مقيم'
    
    if rating >= 4.5:
        return 'ممتاز'
    elif rating >= 3.5:
        return 'جيد جداً'
    elif rating >= 2.5:
        return 'جيد'
    elif rating >= 1.5:
        return 'مقبول'
    else:
        return 'ضعيف'

@register.simple_tag
def rating_progress_bar(rating, max_rating=5, show_percentage=True):
    """Display rating as progress bar"""
    if not rating:
        rating = 0
    
    percentage = (rating / max_rating) * 100
    color_class = rating_color(rating)
    
    html = f'''
    <div class="progress" style="height: 20px;">
        <div class="progress-bar bg-{color_class}" role="progressbar" 
             style="width: {percentage}%" aria-valuenow="{rating}" 
             aria-valuemin="0" aria-valuemax="{max_rating}">
    '''
    
    if show_percentage:
        html += f'{rating:.1f}/{max_rating}'
    
    html += '''
        </div>
    </div>
    '''
    
    return mark_safe(html)

@register.inclusion_tag('suppliers/templatetags/rating_breakdown.html')
def rating_breakdown(supplier):
    """Display detailed rating breakdown"""
    rating_summary = supplier.get_rating_summary()
    return {
        'supplier': supplier,
        'rating_summary': rating_summary
    }

@register.inclusion_tag('suppliers/templatetags/quick_rating_form.html')
def quick_rating_form(supplier, purchase_order=None):
    """Display quick rating form"""
    return {
        'supplier': supplier,
        'purchase_order': purchase_order
    }

@register.filter
def multiply(value, arg):
    """Multiply filter for template calculations"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def percentage(value, total):
    """Calculate percentage"""
    try:
        if total == 0:
            return 0
        return (float(value) / float(total)) * 100
    except (ValueError, TypeError):
        return 0