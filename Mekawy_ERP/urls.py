from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from .error_views import custom_page_not_found_view, custom_server_error_view


def root_redirect(request):
    """Redirect root URL to dashboard or login"""
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    else:
        return redirect('users:login')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', root_redirect, name='root'),  # Handle root URL explicitly
    path('dashboard/', include('dashboard.urls')),  # Change this to avoid conflict

    path('users/', include('users.urls')),
    path('suppliers/', include('suppliers.urls')),
    path('warehouses/', include('warehouses.urls')),
    path('production/', include('production.urls')),
    path('finance/', include('finance.urls')),
    path('hr/', include('hr.urls')),
    path('settings/', include('settings.urls')),
    path('api/', include('api.urls')),
    path('pwa/', include('pwa.urls')),  # Move PWA to specific path
]

handler404 = custom_page_not_found_view
handler500 = custom_server_error_view
# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)