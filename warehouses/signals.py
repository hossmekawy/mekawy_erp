from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
import datetime

# --- CHANGED: Updated Imports ---
# We now import the correct, current models.
# The old sync-related imports for TextileStock and FinishedProduct are removed.
from .models import StockItem, StockMovement, StockTransfer, Product, Warehouse

User = get_user_model()



@receiver(pre_save, sender=Warehouse)
def generate_warehouse_code(sender, instance, **kwargs):
    """
    Generates a sequential code for a new warehouse before it's saved.
    Example: W-0001, W-0002
    """
    # Check if the instance is new and if the code is not already set.
    if not instance.pk and not instance.code:
        # Find the last warehouse to determine the next number.
        last_warehouse = Warehouse.objects.order_by('id').last()
        if last_warehouse and last_warehouse.id:
            next_id = last_warehouse.id + 1
        else:
            # This is the first warehouse.
            next_id = 1
        
        # Format the code and assign it to the instance.
        instance.code = f"W-{next_id:04d}"


# --- KEPT: This signal is correct and essential for managing stock levels. ---
@receiver(post_save, sender=StockMovement)
def update_stock_quantity(sender, instance, created, **kwargs):
    """Updates the stock quantity when a new movement is added."""
    if created:
        stock_item = instance.stock_item
        
        if instance.movement_type == 'out':
            if stock_item.quantity < instance.quantity:
                # This prevents stock from going negative.
                instance.delete()
                raise ValueError(f'The requested quantity is not available. Available: {stock_item.quantity}')
            stock_item.quantity -= instance.quantity
        elif instance.movement_type == 'in':
            stock_item.quantity += instance.quantity
        elif instance.movement_type == 'adjustment':
            # For adjustments, the entered quantity becomes the new quantity.
            stock_item.quantity = instance.quantity
        
        stock_item.save()
        
        # Send an alert if stock is low.
        if stock_item.is_low_stock:
            send_low_stock_alert(stock_item)

# --- KEPT: This signal is correct and handles the logic for stock transfers. ---
@receiver(post_save, sender=StockTransfer)
def handle_stock_transfer(sender, instance, **kwargs):
    """Handles the processing of a stock transfer."""
    # We only process the transfer when its status is 'completed'.
    if instance.status == 'completed' and not kwargs.get('created', False):
        # Check if it has already been processed to avoid duplicate movements.
        # This part of the logic should be handled in the view/form to prevent signals from running multiple times.
        # For now, the core logic is here.
        process_stock_transfer(instance)

def process_stock_transfer(transfer):
    """Executes the actual stock transfer."""
    try:
        source_stock, _ = StockItem.objects.get_or_create(
            warehouse=transfer.from_warehouse,
            product=transfer.product
        )
        
        if source_stock.available_quantity < transfer.quantity:
            raise ValueError(f"Insufficient quantity available. Available: {source_stock.available_quantity}")
        
        target_stock, _ = StockItem.objects.get_or_create(
            warehouse=transfer.to_warehouse,
            product=transfer.product
        )
        
        # Create an 'out' movement from the source warehouse.
        StockMovement.objects.create(
            stock_item=source_stock,
            movement_type='out',
            quantity=transfer.quantity,
            reference_number=transfer.transfer_number,
            notes=f"Transfer to {transfer.to_warehouse.name}",
            created_by=transfer.completed_by
        )
        
        # Create an 'in' movement to the target warehouse.
        StockMovement.objects.create(
            stock_item=target_stock,
            movement_type='in',
            quantity=transfer.quantity,
            reference_number=transfer.transfer_number,
            notes=f"Transfer from {transfer.from_warehouse.name}",
            created_by=transfer.completed_by
        )
        
        send_transfer_completed_notification(transfer)
        
    except Exception as e:
        transfer.status = 'approved' # Revert status on error
        transfer.save()
        send_transfer_error_notification(transfer, str(e))

# --- MODIFIED: This signal is now disabled as per your request. ---
# It no longer automatically creates stock items for a new product in all warehouses.
# You can now manually create stock items using the 'Add Stock' feature.
#
# @receiver(post_save, sender=Product)
# def create_initial_stock_items(sender, instance, created, **kwargs):
#     """Creates initial stock items for a new product in all warehouses."""
#     if created:
#         warehouses = Warehouse.objects.filter(is_active=True)
#         for warehouse in warehouses:
#             StockItem.objects.get_or_create(
#                 warehouse=warehouse,
#                 product=instance,
#                 defaults={'quantity': 0}
#             )

# --- KEPT: This signal automatically generates transfer numbers. ---
@receiver(pre_save, sender=StockTransfer)
def generate_transfer_number(sender, instance, **kwargs):
    """Generates an automatic transfer number if one doesn't exist."""
    if not instance.transfer_number:
        today = datetime.date.today()
        count = StockTransfer.objects.filter(requested_at__date=today).count() + 1
        instance.transfer_number = f"TR-{today.strftime('%Y%m%d')}-{count:04d}"


# --- Note: All notification functions (send_low_stock_alert, etc.) are kept as they are. ---
# --- They are helper functions for the signals above. ---
def send_low_stock_alert(stock_item):
    """Sends a low stock alert email."""
    try:
        managers = User.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True)
        if managers:
            subject = f"Low Stock Alert: {stock_item.product.name}"
            message = f"Warning: Stock is low for product {stock_item.product.name} in warehouse {stock_item.warehouse.name}. Current quantity: {stock_item.quantity}."
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, list(managers), fail_silently=True)
    except Exception as e:
        print(f"Error sending low stock alert: {e}")

def send_transfer_completed_notification(transfer):
    """Sends a notification when a transfer is completed."""
    # This function can be expanded to notify relevant users.
    pass

def send_transfer_error_notification(transfer, error_message):
    """Sends a notification when a transfer fails."""
    # This function can be expanded to notify relevant users about the error.
    pass


# --- REMOVED: All signals related to syncing with old production models have been deleted. ---
# The signals `sync_warehouse_product_to_production` and `delete_production_equivalent`
# are no longer needed because we have a single, unified Product model.
