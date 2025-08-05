from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.utils.cache import add_never_cache_headers

class RoleBasedAccessMiddleware(MiddlewareMixin):
    """
    Middleware to control access based on user roles.
    """
    
    # Define role-based access rules
    ROLE_PERMISSIONS = {
        'admin': ['*'],  # Admin has access to everything
        'manager': ['*'],
        'employee': [
            'dashboard', 'users:profile', 'users:profile_edit',
            'warehouses', 'suppliers', 'production'
        ],
                'warehouse_manager': [
            'dashboard:index',
            'users:profile',
            'users:profile_edit',
            'users:password_change',
            'users:password_change_done',
            'warehouses:*'
        ],
        'warehouse_employee': [
            'warehouses:dashboard',
            'warehouses:stock_list',
            'warehouses:stock_detail',
            'warehouses:movement_list',
            'warehouses:movement_add',
            'warehouses:transfer_list',
            'warehouses:transfer_add',
            'warehouses:product_list',
            'warehouses:product_detail',
        ],
        'production_manager': [
            'warehouses:dashboard',
            'warehouses:stock_list',
            'warehouses:product_list',
            'warehouses:movement_list',
            'production:*',
        ],
        'accountant': [
            'warehouses:dashboard',
            'warehouses:stock_list',
            'warehouses:reports',
            'warehouses:stock_valuation_report',
            'finance:*',
        ],
        'viewer': [
            'dashboard', 'users:profile', 'users:profile_edit','warehouses:dashboard',
            'warehouses:stock_list',
            'warehouses:product_list',
            'warehouses:warehouse_list',
        ]
    }
    
    # URLs that don't require role checking
    EXEMPT_URLS = [
        'users:login', 'users:logout', 'users:password_reset',
        'users:password_reset_done', 'users:password_reset_confirm',
        'users:password_reset_complete'
    ]
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
            
        if request.path.startswith('/admin/'):
            return None
            
        try:
            url_name = request.resolver_match.url_name
            app_name = request.resolver_match.app_name
            full_url_name = f"{app_name}:{url_name}" if app_name else url_name
        except:
            return None

        # Check if the URL is exempt from permission checks.
        if full_url_name in self.EXEMPT_URLS:
            return None
            
        user_role = getattr(request.user, 'role', 'viewer')
        
        if user_role == 'admin':
            return None
            
        allowed_permissions = self.ROLE_PERMISSIONS.get(user_role, [])
        
        has_permission = False
        for permission in allowed_permissions:
            if permission == '*' or permission == full_url_name:
                has_permission = True
                break
            if permission.endswith(':*') and full_url_name.startswith(permission[:-1]):
                has_permission = True
                break
                
        if not has_permission:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'ليس لديك صلاحية للوصول لهذه الصفحة'}, status=403)
            else:
                messages.error(request, 'ليس لديك صلاحية للوصول لهذه الصفحة')
                return redirect('dashboard:index')
                
        return None

# --- NEW MIDDLEWARE TO PREVENT CACHING ---
class NoCacheForAuthenticatedMiddleware:
    """
    Prevents caching of pages for authenticated users.
    This helps avoid one user seeing another user's cached session data.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Add cache-control headers if the user is logged in
        if hasattr(request, 'user') and request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
