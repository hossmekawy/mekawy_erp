from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Avg, Sum, F
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, Payment, 
    SupplierRating, PurchaseOrderDelivery, PurchaseOrderDeliveryItem,
    SupplierPerformanceMetric
)
from warehouses.models import StockItem, StockMovement
import datetime
from decimal import Decimal

User = get_user_model()

@receiver(pre_save, sender=PurchaseOrder)
def generate_po_number(sender, instance, **kwargs):
    """إنشاء رقم أمر شراء تلقائي"""
    if not instance.po_number:
        today = timezone.now().date()
        count = PurchaseOrder.objects.filter(
            created_at__date=today
        ).count() + 1
        instance.po_number = f"PO-{today.strftime('%Y%m%d')}-{count:04d}"

@receiver(post_save, sender=PurchaseOrderItem)
def update_purchase_order_total(sender, instance, **kwargs):
    """تحديث إجمالي أمر الشراء عند تغيير العناصر"""
    po = instance.purchase_order
    subtotal = po.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
    
    po.subtotal = subtotal
    po.total_amount = subtotal + po.tax_amount - po.discount_amount
    po.save(update_fields=['subtotal', 'total_amount'])

@receiver(post_save, sender=PurchaseOrderDeliveryItem)
def update_stock_on_delivery(sender, instance, created, **kwargs):
    """تحديث المخزون عند استلام البضاعة"""
    if created and instance.quality_approved:
        # تحديث الكمية المستلمة في عنصر أمر الشراء
        po_item = instance.purchase_order_item
        po_item.quantity_received += instance.quantity_delivered
        po_item.save()
        
        # إضافة البضاعة للمخزون
        stock_item, created = StockItem.objects.get_or_create(
            warehouse=instance.delivery.warehouse,
            product=po_item.product,
            defaults={'quantity': 0}
        )
        
        # إنشاء حركة مخزون وارد
        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='in',
            quantity=instance.quantity_delivered,
            reference_number=instance.delivery.delivery_number,
            notes=f"استلام من أمر الشراء {po_item.purchase_order.po_number}",
            created_by=instance.delivery.received_by
        )
        
        # التحقق من اكتمال أمر الشراء
        check_purchase_order_completion(po_item.purchase_order)

@receiver(post_save, sender=PurchaseOrder)
def handle_purchase_order_status_change(sender, instance, created, **kwargs):
    """معالجة تغيير حالة أمر الشراء"""
    if not created:
        # إرسال إشعارات حسب الحالة
        if instance.status == 'approved':
            send_po_approved_notification(instance)
        elif instance.status == 'completed':
            send_po_completed_notification(instance)
            # إنشاء طلب تقييم المورد
            create_supplier_rating_request(instance)

@receiver(post_save, sender=SupplierRating)
def update_supplier_rating(sender, instance, created, **kwargs):
    """تحديث تقييم المورد الإجمالي"""
    if created:
        supplier = instance.supplier
        avg_rating = supplier.ratings.aggregate(
            avg=Avg('overall_rating')
        )['avg'] or Decimal('0')
        
        supplier.current_rating = avg_rating
        supplier.save(update_fields=['current_rating'])
        
        # إرسال تنبيه إذا انخفض التقييم عن الحد المعتمد
        if avg_rating < Decimal('3.0'):  # الحد الأدنى 3 من 5
            send_low_rating_alert(supplier, avg_rating)

@receiver(pre_save, sender=Payment)
def generate_payment_number(sender, instance, **kwargs):
    """إنشاء رقم دفعة تلقائي"""
    if not instance.payment_number:
        today = timezone.now().date()
        count = Payment.objects.filter(
            created_at__date=today
        ).count() + 1
        instance.payment_number = f"PAY-{today.strftime('%Y%m%d')}-{count:04d}"

@receiver(pre_save, sender=PurchaseOrderDelivery)
def generate_delivery_number(sender, instance, **kwargs):
    """إنشاء رقم تسليم تلقائي"""
    if not instance.delivery_number:
        today = timezone.now().date()
        count = PurchaseOrderDelivery.objects.filter(
            created_at__date=today
        ).count() + 1
        instance.delivery_number = f"DEL-{today.strftime('%Y%m%d')}-{count:04d}"

def check_purchase_order_completion(purchase_order):
    """التحقق من اكتمال أمر الشراء"""
    all_items_received = all(
        item.is_fully_received for item in purchase_order.items.all()
    )
    
    if all_items_received and purchase_order.status != 'completed':
        purchase_order.status = 'completed'
        purchase_order.actual_delivery_date = timezone.now().date()
        purchase_order.save(update_fields=['status', 'actual_delivery_date'])

def send_po_approved_notification(purchase_order):
    """إرسال إشعار الموافقة على أمر الشراء"""
    try:
        recipients = []
        if purchase_order.created_by and purchase_order.created_by.email:
            recipients.append(purchase_order.created_by.email)
        
        # إضافة مدراء المخازن
        warehouse_managers = User.objects.filter(
            role='warehouse_manager'
        ).values_list('email', flat=True)
        recipients.extend(warehouse_managers)
        
        if recipients:
            subject = f"تم الموافقة على أمر الشراء {purchase_order.po_number}"
            message = f"""
            تم الموافقة على أمر الشراء
            
            رقم الأمر: {purchase_order.po_number}
            المورد: {purchase_order.supplier.name}
            المبلغ الإجمالي: {purchase_order.total_amount}
            تاريخ التسليم المتوقع: {purchase_order.expected_delivery_date}
            وافق عليه: {purchase_order.approved_by.get_full_name() if purchase_order.approved_by else 'غير محدد'}
            
            يمكنكم الآن متابعة عملية التسليم.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال إشعار الموافقة: {e}")

def send_po_completed_notification(purchase_order):
    """إرسال إشعار اكتمال أمر الشراء"""
    try:
        recipients = []
        if purchase_order.created_by and purchase_order.created_by.email:
            recipients.append(purchase_order.created_by.email)
        if purchase_order.approved_by and purchase_order.approved_by.email:
            recipients.append(purchase_order.approved_by.email)
        
        if recipients:
            subject = f"تم إكمال أمر الشراء {purchase_order.po_number}"
            message = f"""
            تم إكمال أمر الشراء بنجاح
            
            رقم الأمر: {purchase_order.po_number}
            المورد: {purchase_order.supplier.name}
            المبلغ الإجمالي: {purchase_order.total_amount}
            تاريخ التسليم الفعلي: {purchase_order.actual_delivery_date}
            
            تم استلام جميع العناصر وإضافتها للمخزون.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال إشعار الإكمال: {e}")

def create_supplier_rating_request(purchase_order):
    """إنشاء طلب تقييم المورد"""
    try:
        # إرسال إشعار للمسؤولين لتقييم المورد
        managers = User.objects.filter(
            role__in=['admin', 'manager', 'warehouse_manager']
        ).values_list('email', flat=True)
        
        if managers:
            subject = f"طلب تقييم المورد - {purchase_order.supplier.name}"
            message = f"""
            يرجى تقييم أداء المورد
            
            المورد: {purchase_order.supplier.name}
            أمر الشراء: {purchase_order.po_number}
            تاريخ الإكمال: {purchase_order.actual_delivery_date}
            
            يرجى الدخول للنظام وتقييم المورد بناءً على:
            - جودة المنتجات
            - الالتزام بالتسليم
            - تنافسية الأسعار
            - خدمة العملاء
            - التواصل
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال طلب التقييم: {e}")

def send_low_rating_alert(supplier, rating):
    """إرسال تنبيه انخفاض تقييم المورد"""
    try:
        managers = User.objects.filter(
            role__in=['admin', 'manager']
        ).values_list('email', flat=True)
        
        if managers:
            subject = f"تحذير: انخفاض تقييم المورد - {supplier.name}"
            message = f"""
            تحذير: انخفض تقييم المورد عن الحد المعتمد
            
            المورد: {supplier.name}
            التقييم الحالي: {rating}/5
            الحد الأدنى المعتمد: 3/5
            
            يرجى مراجعة أداء المورد واتخاذ الإجراء المناسب.
            قد تحتاجون إلى:
            - مناقشة المشاكل مع المورد
            - وضع خطة تحسين
            - البحث عن موردين بديلين
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال تنبيه انخفاض التقييم: {e}")

def check_overdue_purchase_orders():
    """فحص أوامر الشراء المتأخرة - يتم استدعاؤها من مهمة دورية"""
    overdue_orders = PurchaseOrder.objects.filter(
        status__in=['pending', 'approved', 'in_delivery'],
        expected_delivery_date__lt=timezone.now().date()
    )
    
    for order in overdue_orders:
        send_overdue_order_alert(order)

def send_overdue_order_alert(purchase_order):
    """إرسال تنبيه أمر الشراء المتأخر"""
    try:
        recipients = []
        if purchase_order.created_by and purchase_order.created_by.email:
            recipients.append(purchase_order.created_by.email)
        
        managers = User.objects.filter(
            role__in=['admin', 'manager', 'warehouse_manager']
        ).values_list('email', flat=True)
        recipients.extend(managers)
        
        if recipients:
            subject = f"تحذير: تأخير في أمر الشراء {purchase_order.po_number}"
            message = f"""
            تحذير: أمر شراء متأخر
            
            رقم الأمر: {purchase_order.po_number}
            المورد: {purchase_order.supplier.name}
            تاريخ التسليم المتوقع: {purchase_order.expected_delivery_date}
            عدد أيام التأخير: {purchase_order.days_overdue}
            الحالة الحالية: {purchase_order.get_status_display()}
            
            يرجى المتابعة مع المورد لمعرفة سبب التأخير.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(set(recipients)),  # إزالة التكرار
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال تنبيه التأخير: {e}")

def calculate_supplier_performance_metrics():
    """حساب مقاييس أداء الموردين - مهمة دورية شهرية"""
    try:
        # حساب المقاييس للشهر الماضي
        today = timezone.now().date()
        last_month_start = today.replace(day=1) - datetime.timedelta(days=1)
        last_month_start = last_month_start.replace(day=1)
        last_month_end = today.replace(day=1) - datetime.timedelta(days=1)
        
        suppliers = Supplier.objects.filter(is_active=True)
        
        for supplier in suppliers:
            metric, created = SupplierPerformanceMetric.objects.get_or_create(
                supplier=supplier,
                period_start=last_month_start,
                period_end=last_month_end
            )
            metric.calculate_metrics()
            
    except Exception as e:
        print(f"خطأ في حساب مقاييس الأداء: {e}")

def check_document_expiry():
    """فحص انتهاء صلاحية مستندات الموردين - مهمة دورية يومية"""
    try:
        from .models import SupplierDocument
        
        # المستندات التي ستنتهي خلال 30 يوم
        expiring_docs = SupplierDocument.objects.filter(
            expiry_date__lte=timezone.now().date() + datetime.timedelta(days=30),
            expiry_date__gt=timezone.now().date()
        )
        
        # المستندات المنتهية الصلاحية
        expired_docs = SupplierDocument.objects.filter(
            expiry_date__lt=timezone.now().date()
        )
        
        if expiring_docs.exists() or expired_docs.exists():
            send_document_expiry_alert(expiring_docs, expired_docs)
            
    except Exception as e:
        print(f"خطأ في فحص انتهاء المستندات: {e}")

def send_document_expiry_alert(expiring_docs, expired_docs):
    """إرسال تنبيه انتهاء صلاحية المستندات"""
    try:
        managers = User.objects.filter(
            role__in=['admin', 'manager']
        ).values_list('email', flat=True)
        
        if managers:
            subject = "تحذير: انتهاء صلاحية مستندات الموردين"
            message = "تحذير: مستندات موردين تحتاج لتجديد\n\n"
            
            if expired_docs.exists():
                message += "مستندات منتهية الصلاحية:\n"
                for doc in expired_docs:
                    message += f"- {doc.supplier.name}: {doc.title} (انتهت في {doc.expiry_date})\n"
                message += "\n"
            
            if expiring_docs.exists():
                message += "مستندات ستنتهي قريباً:\n"
                for doc in expiring_docs:
                    message += f"- {doc.supplier.name}: {doc.title} (تنتهي في {doc.expiry_date})\n"
            
            message += "\nيرجى التواصل مع الموردين لتجديد المستندات."
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال تنبيه انتهاء المستندات: {e}")

# إشارات إضافية لتحسين الأداء
@receiver(post_save, sender=Supplier)
def create_supplier_code(sender, instance, created, **kwargs):
    """إنشاء كود المورد تلقائياً إذا لم يكن موجوداً"""
    if created and not instance.code:
        # إنشاء كود بناءً على اسم المورد والرقم التسلسلي
        name_part = ''.join([c for c in instance.name[:3].upper() if c.isalpha()])
        if len(name_part) < 3:
            name_part = name_part.ljust(3, 'X')
        
        count = Supplier.objects.count()
        instance.code = f"SUP-{name_part}-{count:04d}"
        instance.save(update_fields=['code'])

@receiver(post_delete, sender=PurchaseOrderItem)
def update_po_total_on_delete(sender, instance, **kwargs):
    """تحديث إجمالي أمر الشراء عند حذف عنصر"""
    po = instance.purchase_order
    subtotal = po.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
    
    po.subtotal = subtotal
    po.total_amount = subtotal + po.tax_amount - po.discount_amount
    po.save(update_fields=['subtotal', 'total_amount'])

@receiver(post_save, sender=Payment)
def update_supplier_balance(sender, instance, created, **kwargs):
    """تحديث رصيد المورد عند إضافة دفعة"""
    if created and instance.status == 'completed':
        # يمكن إضافة منطق تحديث رصيد المورد هنا
        # حسب متطلبات النظام المحاسبي
        pass

# دالة مساعدة لإرسال الإشعارات
def send_notification_to_roles(subject, message, roles, additional_emails=None):
    """إرسال إشعار لأدوار محددة"""
    try:
        recipients = list(User.objects.filter(
            role__in=roles,
            email__isnull=False
        ).values_list('email', flat=True))
        
        if additional_emails:
            recipients.extend(additional_emails)
        
        if recipients:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(set(recipients)),  # إزالة التكرار
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال الإشعار: {e}")

# دالة للتحقق من حدود الائتمان
def check_credit_limit(supplier, amount):
    """التحقق من حد الائتمان للمورد"""
    if supplier.credit_limit <= 0:
        return True  # لا يوجد حد ائتمان
    
    pending_amount = supplier.pending_amount
    if pending_amount + amount > supplier.credit_limit:
        return False
    
    return True

# إشارة للتحقق من حد الائتمان عند إنشاء أمر شراء
@receiver(pre_save, sender=PurchaseOrder)
def check_supplier_credit_limit(sender, instance, **kwargs):
    """التحقق من حد الائتمان قبل حفظ أمر الشراء"""
    if instance.pk is None:  # أمر جديد
        if not check_credit_limit(instance.supplier, instance.total_amount):
            # إرسال تنبيه لتجاوز حد الائتمان
            send_credit_limit_alert(instance.supplier, instance.total_amount)

def send_credit_limit_alert(supplier, amount):
    """إرسال تنبيه تجاوز حد الائتمان"""
    try:
        managers = User.objects.filter(
            role__in=['admin', 'manager', 'accountant']
        ).values_list('email', flat=True)
        
        if managers:
            subject = f"تحذير: تجاوز حد الائتمان - {supplier.name}"
            message = f"""
            تحذير: محاولة تجاوز حد الائتمان
            
            المورد: {supplier.name}
            حد الائتمان: {supplier.credit_limit}
            المبلغ المعلق حالياً: {supplier.pending_amount}
            المبلغ المطلوب: {amount}
            إجمالي المبلغ: {supplier.pending_amount + amount}
            
            يرجى مراجعة الطلب والموافقة عليه إذا لزم الأمر.
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
    except Exception as e:
        print(f"خطأ في إرسال تنبيه حد الائتمان: {e}")

@receiver(post_save, sender=SupplierRating)
def update_supplier_rating_on_save(sender, instance, created, **kwargs):
    """تحديث تقييم المورد عند إضافة أو تعديل تقييم"""
    supplier = instance.supplier
    
    # Calculate new average rating
    avg_rating = supplier.ratings.aggregate(
        avg=Avg('overall_rating')
    )['avg']
    
    if avg_rating:
        supplier.current_rating = round(avg_rating, 2)
        supplier.save(update_fields=['current_rating'])

@receiver(post_delete, sender=SupplierRating)
def update_supplier_rating_on_delete(sender, instance, **kwargs):
    """تحديث تقييم المورد عند حذف تقييم"""
    supplier = instance.supplier
    
    # Calculate new average rating
    avg_rating = supplier.ratings.aggregate(
        avg=Avg('overall_rating')
    )['avg']
    
    supplier.current_rating = round(avg_rating, 2) if avg_rating else 0
    supplier.save(update_fields=['current_rating'])