# production/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from .models import ExternalManufacturer, AssemblyProcess, ManufacturerProductPrice
from finance.models import Account, Transaction

@receiver(post_save, sender=ExternalManufacturer)
def create_finance_account_for_manufacturer(sender, instance, created, **kwargs):
    """
    Automatically creates a financial account for a new external manufacturer.
    """
    if created:
        Account.objects.create(
            name=f"حساب المصنع: {instance.name}",
            account_type='LIABILITY',
            manufacturer=instance
        )

@receiver(post_save, sender=AssemblyProcess)
def create_manufacturing_debt_transaction(sender, instance, created, **kwargs):
    """
    When goods are received from an external manufacturer in an AssemblyProcess,
    create a "MANUFACTURING_DEBT" transaction to record the liability.
    """
    # Proceed only if the process is linked to an external manufacturer and has received items
    if instance.external_manufacturer and instance.quantity_received > 0:
        # Avoid creating duplicate transactions
        content_type = ContentType.objects.get_for_model(instance)
        if Transaction.objects.filter(content_type=content_type, object_id=instance.id).exists():
            return # A transaction for this assembly process already exists

        try:
            # Find the manufacturer's financial account
            manufacturer_account = Account.objects.get(manufacturer=instance.external_manufacturer)
            
            # Get the product being manufactured
            product = instance.production_order.product
            
            # Find the agreed price for this product from this manufacturer
            price_record = ManufacturerProductPrice.objects.get(
                manufacturer=instance.external_manufacturer,
                product=product
            )
            price_per_unit = price_record.price
            
            # Calculate total cost
            total_cost = Decimal(instance.quantity_received) * price_per_unit
            
            # Create the debt transaction
            if total_cost > 0:
                # This transaction increases the manufacturer's account balance (our liability)
                manufacturer_account.balance += total_cost
                manufacturer_account.save()

                Transaction.objects.create(
                    account=manufacturer_account,
                    type='MANUFACTURING_DEBT',
                    amount=total_cost,
                    description=f"تكلفة استلام عدد {instance.quantity_received} قطعة من المنتج '{product.name}' من المصنع '{instance.external_manufacturer.name}' (أمر إنتاج: {instance.production_order.order_number})",
                    reference=f"Assembly-{instance.id}",
                    content_object=instance
                )

        except Account.DoesNotExist:
            # Handle case where account doesn't exist (should not happen due to the other signal)
            pass
        except ManufacturerProductPrice.DoesNotExist:
            # Handle case where a price has not been set for this product/manufacturer
            # You might want to log this or create a notification for the user
            pass

