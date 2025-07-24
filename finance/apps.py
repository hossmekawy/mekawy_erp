# finance/apps.py

from django.apps import AppConfig

class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = 'الإدارة المالية'

    def ready(self):
        # Import signals to ensure they are connected when the app is ready.
        from . import signals
