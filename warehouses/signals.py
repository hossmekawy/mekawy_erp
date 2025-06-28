from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from .models import Product as WarehouseProduct , Warehouse
from .models import StockItem, StockMovement, StockTransfer, Product
from production.models import TextileStock, FinishedProduct

import datetime

User = get_user_model()

@receiver(post_save, sender=StockMovement)
def update_stock_quantity(sender, instance, created, **kwargs):
    """تحديث كمية المخزون عند إضافة حركة جديدة"""
    if created:
        stock_item = instance.stock_item
        
        # Add validation for 'out' movements
        if instance.movement_type == 'out':
            if stock_item.quantity < instance.quantity:
                # Rollback the movement creation
                instance.delete()
                raise ValueError(f'الكمية المطلوبة غير متوفرة. المتاح: {stock_item.quantity}')
            stock_item.quantity -= instance.quantity
        elif instance.movement_type == 'in':
            stock_item.quantity += instance.quantity
        elif instance.movement_type == 'adjustment':
            # في حالة التسوية، الكمية المدخلة هي الكمية الجديدة
            stock_item.quantity = instance.quantity
        
        stock_item.save()
        
        # إرسال تنبيه إذا كان المخزون منخفض
        if stock_item.is_low_stock:
            send_low_stock_alert(stock_item)

@receiver(post_save, sender=StockTransfer)
def handle_stock_transfer(sender, instance, created, **kwargs):
    """معالجة تحويل المخزون"""
    if not created:
        # إذا تم تغيير الحالة إلى مكتمل
        if instance.status == 'completed' and instance.completed_at:
            process_stock_transfer(instance)
        elif instance.status == 'approved' and instance.approved_at:
            send_transfer_approved_notification(instance)

def process_stock_transfer(transfer):
    """تنفيذ تحويل المخزون فعلياً"""
    try:
        # البحث عن عنصر المخزون في المخزن المصدر
        source_stock, created = StockItem.objects.get_or_create(
            warehouse=transfer.from_warehouse,
            product=transfer.product,
            defaults={'quantity': 0}
        )
        
        # التحقق من توفر الكمية
        if source_stock.available_quantity < transfer.quantity:
            raise ValueError(f"الكمية المتاحة غير كافية. المتاح: {source_stock.available_quantity}")
        
        # البحث عن عنصر المخزون في المخزن المستهدف
        target_stock, created = StockItem.objects.get_or_create(
            warehouse=transfer.to_warehouse,
            product=transfer.product,
            defaults={'quantity': 0}
        )
        
        # إنشاء حركة صادر من المخزن المصدر
        StockMovement.objects.create(
            stock_item=source_stock,
            movement_type='out',
            quantity=transfer.quantity,
            reference_number=transfer.transfer_number,
            notes=f"تحويل إلى {transfer.to_warehouse.name}",
            created_by=transfer.completed_by
        )
        
        # إنشاء حركة وارد للمخزن المستهدف
        StockMovement.objects.create(
            stock_item=target_stock,
            movement_type='in',
            quantity=transfer.quantity,
            reference_number=transfer.transfer_number,
            notes=f"تحويل من {transfer.from_warehouse.name}",
            created_by=transfer.completed_by
        )
        
        # إرسال إشعار بإتمام التحويل
        send_transfer_completed_notification(transfer)
        
    except Exception as e:
        # في حالة حدوث خطأ، إرجاع الحالة إلى معتمد
        transfer.status = 'approved'
        transfer.save()
        send_transfer_error_notification(transfer, str(e))

def send_low_stock_alert(stock_item):
    """إرسال تنبيه المخزون المنخفض"""
    try:
        # البحث عن المدراء والمسؤولين
        managers = User.objects.filter(
            role__in=['admin', 'warehouse_manager']
        ).values_list('email', flat=True)
        
        if managers:
            subject = f"تنبيه: مخزون منخفض - {stock_item.product.name}"
            message = f"""
            تحذير: المخزون منخفض
            
            المنتج: {stock_item.product.name}
            الكود: {stock_item.product.code}
            المخزن: {stock_item.warehouse.name}
            الكمية الحالية: {stock_item.quantity}
            الحد الأدنى: {stock_item.product.min_stock_level}
            
            يرجى اتخاذ الإجراء اللازم لتجديد المخزون.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال تنبيه المخزون المنخفض: {e}")

def send_transfer_approved_notification(transfer):
    """إرسال إشعار الموافقة على التحويل"""
    try:
        if transfer.requested_by and transfer.requested_by.email:
            subject = f"تم الموافقة على التحويل رقم {transfer.transfer_number}"
            message = f"""
            تم الموافقة على طلب التحويل
            
            رقم التحويل: {transfer.transfer_number}
            المنتج: {transfer.product.name}
            من المخزن: {transfer.from_warehouse.name}
            إلى المخزن: {transfer.to_warehouse.name}
            الكمية: {transfer.quantity}
            وافق عليه: {transfer.approved_by.get_full_name() if transfer.approved_by else 'غير محدد'}
            تاريخ الموافقة: {transfer.approved_at}
            
            يمكنك الآن تنفيذ التحويل.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [transfer.requested_by.email],
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال إشعار الموافقة: {e}")

def send_transfer_completed_notification(transfer):
    """إرسال إشعار إتمام التحويل"""
    try:
        recipients = []
        if transfer.requested_by and transfer.requested_by.email:
            recipients.append(transfer.requested_by.email)
        if transfer.approved_by and transfer.approved_by.email:
            recipients.append(transfer.approved_by.email)
        
        if recipients:
            subject = f"تم إتمام التحويل رقم {transfer.transfer_number}"
            message = f"""
            تم إتمام التحويل بنجاح
            
            رقم التحويل: {transfer.transfer_number}
            المنتج: {transfer.product.name}
            من المخزن: {transfer.from_warehouse.name}
            إلى المخزن: {transfer.to_warehouse.name}
            الكمية: {transfer.quantity}
            أتمه: {transfer.completed_by.get_full_name() if transfer.completed_by else 'غير محدد'}
            تاريخ الإتمام: {transfer.completed_at}
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال إشعار الإتمام: {e}")

def send_transfer_error_notification(transfer, error_message):
    """إرسال إشعار خطأ في التحويل"""
    try:
        managers = User.objects.filter(
            role__in=['admin', 'warehouse_manager']
        ).values_list('email', flat=True)
        
        if managers:
            subject = f"خطأ في تنفيذ التحويل رقم {transfer.transfer_number}"
            message = f"""
            حدث خطأ أثناء تنفيذ التحويل
            
            رقم التحويل: {transfer.transfer_number}
            المنتج: {transfer.product.name}
            من المخزن: {transfer.from_warehouse.name}
            إلى المخزن: {transfer.to_warehouse.name}
            الكمية: {transfer.quantity}
            
            رسالة الخطأ: {error_message}
            
            يرجى مراجعة التحويل وإعادة المحاولة.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال إشعار الخطأ: {e}")

@receiver(pre_save, sender=StockTransfer)
def generate_transfer_number(sender, instance, **kwargs):
    """إنشاء رقم تحويل تلقائي"""
    if not instance.transfer_number:
        today = datetime.date.today()
        count = StockTransfer.objects.filter(
            requested_at__date=today
        ).count() + 1
        instance.transfer_number = f"TR-{today.strftime('%Y%m%d')}-{count:04d}"

@receiver(post_save, sender=Product)
def create_initial_stock_items(sender, instance, created, **kwargs):
    """إنشاء عناصر مخزون أولية للمنتج الجديد في جميع المخازن"""
    if created:
        from .models import Warehouse
        warehouses = Warehouse.objects.filter(is_active=True)
        
        for warehouse in warehouses:
            StockItem.objects.get_or_create(
                warehouse=warehouse,
                product=instance,
                defaults={'quantity': 0}
            )



@receiver(post_save, sender=WarehouseProduct)
def sync_warehouse_product_to_production(sender, instance, created, **kwargs):
    """
    Creates a corresponding TextileStock or FinishedProduct when a WarehouseProduct
    is created.
    
    Uses bulk_create to prevent the reciprocal signals in the 'production' app
    from firing and causing a race condition or an integrity error.
    """
    if created:
        if instance.product_type == 'fabric' and not hasattr(instance, 'textile_equivalent'):
            default_warehouse = Warehouse.objects.filter(is_active=True).first()
            
            # Create an in-memory instance of TextileStock
            textile_to_create = TextileStock(
                warehouse_product=instance,
                name=instance.name.split(' - ')[0] if ' - ' in instance.name else instance.name,
                color=instance.name.split(' - ')[1] if ' - ' in instance.name else 'N/A',
                cost_per_meter=instance.cost_price,
                warehouse=default_warehouse,
                width=0, # Sensible default
            )
            # Use bulk_create to avoid triggering post_save signals on TextileStock
            TextileStock.objects.bulk_create([textile_to_create])

        elif instance.product_type == 'finished' and not hasattr(instance, 'finished_product_origin'):
            # Create an in-memory instance of FinishedProduct
            finished_product_to_create = FinishedProduct(
                warehouse_product=instance,
                name=instance.name,
                code=instance.code,
                base_cost=instance.cost_price,
                selling_price=instance.selling_price,
                fabric_quantity_per_piece=0, # Sensible default
            )
            # Use bulk_create to avoid triggering post_save signals on FinishedProduct
            FinishedProduct.objects.bulk_create([finished_product_to_create])

@receiver(post_delete, sender=WarehouseProduct)
def delete_production_equivalent_on_product_delete(sender, instance, **kwargs):
    """
    Deletes the corresponding TextileStock or FinishedProduct when a WarehouseProduct is deleted.
    This ensures the two-way sync is complete and prevents orphaned records.
    """
    # Use a try-except block to gracefully handle cases where the related object might not exist.
    try:
        # Check for and delete the related TextileStock if it exists.
        if hasattr(instance, 'textile_equivalent') and instance.textile_equivalent:
            instance.textile_equivalent.delete()
    except TextileStock.DoesNotExist:
        # The object was already gone, so we don't need to do anything.
        pass

    try:
        # Check for and delete the related FinishedProduct if it exists.
        if hasattr(instance, 'finished_product_origin') and instance.finished_product_origin:
            instance.finished_product_origin.delete()
    except FinishedProduct.DoesNotExist:
        # The object was already gone, so we don't need to do anything.
        pass