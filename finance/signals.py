# finance/signals.py
# This file should be imported in your finance/apps.py file.

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
import logging

# Import your ERP's models that need financial accounts
# This is an example; you will need to adjust the import path
# from crm.models import Customer 
from production.models import ExternalManufacturer

from .models import Account, AccountCategory

logger = logging.getLogger(__name__)

def create_linked_account(instance, name_prefix, category_name, category_type):
    """
    Generic helper function to create a linked financial account for a given model instance.
    """
    try:
        category, _ = AccountCategory.objects.get_or_create(
            name=category_name,
            defaults={'category_type': category_type}
        )
        
        account_name = f"{name_prefix}: {instance.name}"
        content_type = ContentType.objects.get_for_model(instance)

        # Use update_or_create to handle both creation and name changes of the owner object
        Account.objects.update_or_create(
            owner_content_type=content_type,
            owner_object_id=instance.pk,
            defaults={
                'name': account_name,
                'category': category,
                'is_active': getattr(instance, 'is_active', True) # Assumes the linked model has an 'is_active' field
            }
        )
        logger.info(f"Financial account ensured for {instance._meta.verbose_name}: {instance.name}")
    except Exception as e:
        logger.error(f"Error in account creation signal for {instance.name}: {e}")

@receiver(post_save, sender=ExternalManufacturer)
def create_manufacturer_account(sender, instance, **kwargs):
    """
    Creates an 'Accounts Payable' sub-account for an ExternalManufacturer.
    """
    create_linked_account(
        instance=instance,
        name_prefix=_("ذمم دائنة"),
        category_name=_("الذمم الدائنة (Accounts Payable)"),
        category_type='liability'
    )

# Example for a Customer model if you have one in a 'crm' app
# @receiver(post_save, sender=Customer)
# def create_customer_account(sender, instance, **kwargs):
#     """
#     Creates an 'Accounts Receivable' sub-account for a Customer.
#     """
#     create_linked_account(
#         instance=instance,
#         name_prefix=_("ذمم مدينة"),
#         category_name=_("الذمم المدينة (Accounts Receivable)"),
#         category_type='asset'
#     )

