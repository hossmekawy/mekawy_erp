from django.apps import AppConfig


class WarehousesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'warehouses'
    verbose_name = 'إدارة المخازن'
    
    def ready(self):
        from . import signals
