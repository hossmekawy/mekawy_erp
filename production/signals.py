# production/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from .models import ExternalManufacturer
from finance.models import Account, AccountCategory
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ExternalManufacturer)
def create_or_update_manufacturer_account(sender, instance, created, **kwargs):
    """
    Signal to automatically create or update a liability Account in the finance app
    whenever an ExternalManufacturer is created or its name changes.
    """
    try:
        category_name = _("Accounts Payable - External Manufacturers")
        liability_category, _ = AccountCategory.objects.get_or_create(
            name=category_name,
            defaults={'category_type': 'liability'}
        )
        account_name = f"{_('Vendor Account')}: {instance.name}"
        content_type = ContentType.objects.get_for_model(instance)

        Account.objects.update_or_create(
            owner_content_type=content_type,
            owner_object_id=instance.pk,
            defaults={
                'name': account_name,
                'category': liability_category,
                'is_active': True
            }
        )
        logger.info(f"Financial account ensured for manufacturer: {instance.name}")
    except Exception as e:
        logger.error(f"Error in manufacturer account signal for {instance.name}: {e}")