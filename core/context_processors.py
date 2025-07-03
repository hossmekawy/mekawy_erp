import os
import json
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch
from django.conf import settings
from django.utils.text import slugify
from settings.models import Setting

User = get_user_model()

def global_context(request):
    """
    Adds general-purpose variables to all templates.
    """
    return {'current_year': timezone.now().year}

def theme_context(request):
    """
    Adds theme-related settings to the context for dynamic styling.
    """
    context = {}
    settings_keys = {
        'sidebar_bg_color': '#343a40',
        'sidebar_text_color': '#ffffff',
        'site_logo_url': None,
        'site_name': 'Mekawy ERP'
    }
    for key, default_value in settings_keys.items():
        try:
            # For the logo, we need to ensure the value is not empty
            setting = Setting.objects.get(key=key)
            context[key] = setting.value if setting.value else default_value
        except Setting.DoesNotExist:
            context[key] = default_value
    return context

def sidebar_context(request):
    """
    Adds the sidebar navigation structure from a JSON file.
    This version correctly handles nested submenus.
    """
    nav_file = os.path.join(settings.BASE_DIR, 'sidebar_nav.json')
    try:
        with open(nav_file, 'r', encoding='utf-8') as f:
            nav_structure = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'sidebar_nav_items': {}}

    resolved_nav = {}
    user_role = getattr(request.user, 'role', None)

    for section_title, section_details in nav_structure.items():
        # Determine if this section has a submenu or is a direct group of links
        has_submenu = 'submenu' in section_details
        
        # Get the main properties for the section
        main_icon = section_details.get('icon', 'fas fa-folder-open') if has_submenu else 'fas fa-folder-open'
        main_roles = section_details.get('roles', []) if has_submenu else ['*'] # Top-level roles only apply to submenu groups
        
        # Decide which dictionary contains the links to process
        links_to_process = section_details.get('submenu', section_details)

        # Check if the user has access to the entire section (for submenu groups)
        if has_submenu and '*' not in main_roles and (not request.user.is_authenticated or user_role not in main_roles):
            continue

        resolved_links = {}
        for label, details in links_to_process.items():
            # Check if details is a dictionary (to avoid errors on keys like "title")
            if not isinstance(details, dict):
                continue
            
            link_roles = details.get('roles', [])
            
            # Check if user has access to this specific link
            if '*' in link_roles or (request.user.is_authenticated and user_role in link_roles):
                is_modal = details.get('is_modal', False)
                url_name = details.get('url_name')
                url = '#' # Default URL

                if url_name:
                    if is_modal:
                        url = url_name # For modals, the url_name is the selector itself (e.g., '#logoutModal')
                    else:
                        try:
                            url = reverse(url_name)
                        except NoReverseMatch:
                            url = '#' # URL name might not exist, fail gracefully

                resolved_links[label] = {
                    'resolved_url': url,
                    'icon': details.get('icon', 'fas fa-link'),
                    'is_modal': is_modal
                }

        # If any links were resolved for the user, add the whole section to the nav
        if resolved_links:
            section_id = slugify(section_title, allow_unicode=True)
            resolved_nav[section_title] = {
                'id': section_id,
                'icon': main_icon,
                'links': resolved_links
            }

    return {'sidebar_nav_items': resolved_nav}