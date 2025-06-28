from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal

# Assuming these models are in the same 'production' app
from .models import FinishedProduct, TextileStock, CuttingProcess, BOMItem, ProductionOrder

# Models from the 'warehouses' app
from warehouses.models import Product as WarehouseProduct, StockItem, StockMovement, Category, Unit

@receiver(post_save, sender=FinishedProduct)
def sync_finished_product_with_warehouse(sender, instance, created, **kwargs):
    """
    Create or update a corresponding warehouse Product when a FinishedProduct is saved.
    This ensures that finished goods are trackable in the inventory system.
    """
    if created:
        product, _ = WarehouseProduct.objects.get_or_create(
            code=instance.code,
            defaults={
                'name': instance.name,
                'product_type': 'finished',
                'unit': 'piece',
                'cost_price': getattr(instance, 'base_cost', 0),
                'selling_price': getattr(instance, 'selling_price', 0),
                'is_active': instance.is_active,
            }
        )
        if not getattr(instance, 'warehouse_product', None):
             instance.warehouse_product = product
             instance.save(update_fields=['warehouse_product'])
    else:
        if getattr(instance, 'warehouse_product', None):
            product = instance.warehouse_product
            product.name = instance.name
            product.code = instance.code
            product.cost_price = getattr(instance, 'base_cost', 0)
            product.selling_price = getattr(instance, 'selling_price', 0)
            product.is_active = instance.is_active
            product.save()

@receiver(post_delete, sender=FinishedProduct)
def deactivate_warehouse_product_on_finished_product_delete(sender, instance, **kwargs):
    """
    When a FinishedProduct is deleted, this deactivates (soft-deletes) the corresponding
    product in the warehouse system instead of a hard delete.
    """
    if getattr(instance, 'warehouse_product', None):
        instance.warehouse_product.is_active = False
        instance.warehouse_product.save()

@receiver(post_save, sender=TextileStock)
def sync_textile_with_warehouse_product(sender, instance, created, **kwargs):
    """
    Creates or updates a corresponding WarehouseProduct when a TextileStock is saved.
    Also ensures a StockItem exists for the textile in its designated warehouse.
    """
    if created:
        if not getattr(instance, 'warehouse_product', None):
            fabric_category, _ = Category.objects.get_or_create(name='أقمشه')
            product_name = f"{instance.name} - {instance.color}"
            product_code = f"TEX-{instance.id}"

            product, _ = WarehouseProduct.objects.get_or_create(
                code=product_code,
                defaults={
                    'name': product_name,
                    'product_type': 'fabric',
                    'unit': 'meter',
                    'cost_price': instance.cost_per_meter,
                    'is_active': instance.is_active,
                    'category': fabric_category,
                }
            )
            instance.warehouse_product = product
            instance.save(update_fields=['warehouse_product'])
    else:
        if getattr(instance, 'warehouse_product', None):
            product = instance.warehouse_product
            product.name = f"{instance.name} - {instance.color}"
            product.cost_price = instance.cost_per_meter
            product.is_active = instance.is_active
            product.save()

    if getattr(instance, 'warehouse', None) and getattr(instance, 'warehouse_product', None):
        StockItem.objects.get_or_create(
            warehouse=instance.warehouse,
            product=instance.warehouse_product,
            defaults={'quantity': Decimal('0.0')}
        )


@receiver(post_delete, sender=TextileStock)
def deactivate_warehouse_product_on_textile_delete(sender, instance, **kwargs):
    """
    When a TextileStock item is deleted, this deactivates the corresponding warehouse product.
    """
    if getattr(instance, 'warehouse_product', None):
        instance.warehouse_product.is_active = False
        instance.warehouse_product.save()


# --- CORRECTED SIGNAL FOR CUTTING PROCESS COMPLETION (WITH PER-PIECE LOGIC) ---

@receiver(post_save, sender=CuttingProcess)
def update_stock_and_bom_on_cutting_complete(sender, instance, **kwargs):
    """
    When a cutting process is marked as complete, this signal will:
    1. Create a stock movement to deduct the TOTAL used fabric from the warehouse inventory.
    2. **MODIFIED**: Update the fabric item in the BOM with the actual calculated per-piece meterage
       from the cutting process for future accuracy.
    """
    # Only proceed if the process is marked as complete and has a valid calculated meterage.
    if not instance.is_completed:
        return

    production_order = instance.production_order
    bom = getattr(production_order, 'bom_version', None)
    total_fabric_used = getattr(instance, 'total_fabric_used', Decimal('0.0'))
    
    # --- NEW: Get the calculated meterage per piece from the instance ---
    calculated_meterage_per_piece = getattr(instance, 'single_layer_meterage', None)

    if not bom or not total_fabric_used or total_fabric_used <= 0:
        return

    # IDEMPOTENCY CHECK: Prevents the signal from running more than once for the same process.
    reference_number = f"CUT-{production_order.order_number}"
    if StockMovement.objects.filter(reference_number=reference_number).exists():
        return # Exit if stock has already been deducted for this cutting process.

    try:
        # --- START OF LOGIC ---
        
        # 1. Find the corresponding stock item for the fabric in the warehouse.
        fabric_warehouse_product = production_order.textile_stock.warehouse_product
        fabric_stock_item = StockItem.objects.get(
            warehouse=production_order.textile_stock.warehouse,
            product=fabric_warehouse_product
        )

        # 2. Create the stock movement to deduct the TOTAL used quantity.
        StockMovement.objects.create(
            stock_item=fabric_stock_item,
            movement_type='out',
            quantity=total_fabric_used,
            reference_number=reference_number,
            notes=f"استهلاك قماش لعملية القص الخاصة بأمر الإنتاج #{production_order.order_number}",
            created_by=instance.cutter
        )
        
        # 3. --- CORE CHANGE ---
        # If a valid per-piece meterage was calculated, update the BOM.
        if calculated_meterage_per_piece and calculated_meterage_per_piece > 0:
            bom_item_to_update = BOMItem.objects.get(
                bom=bom,
                material=fabric_warehouse_product
            )
            
            # Update the BOM item's quantity with the new, more accurate value.
            bom_item_to_update.quantity = calculated_meterage_per_piece
            bom_item_to_update.save()
            print(f"BOM for {bom.product.name} updated with new fabric quantity: {calculated_meterage_per_piece}")

    except BOMItem.DoesNotExist:
        print(f"Warning: Fabric '{fabric_warehouse_product.name}' used in order '{production_order.order_number}' was not found in BOM '{bom}'. BOM not updated.")
        pass
    except StockItem.DoesNotExist:
        print(f"Error: StockItem for fabric '{fabric_warehouse_product.name}' not found in warehouse. Stock not updated for order {production_order.order_number}.")
        pass
    except Exception as e:
        # It's good practice to log errors for debugging.
        import logging
        logging.error(f"An error occurred in the cutting completion signal for order {production_order.order_number}: {e}")
