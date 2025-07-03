from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    # Main settings page
    path('', views.settings_view, name='general'),
    
    # Backup and Restore URLs
    path('backup/create/', views.create_backup, name='create_backup'),
    path('backup/import/', views.import_backup, name='import_backup'),
]
