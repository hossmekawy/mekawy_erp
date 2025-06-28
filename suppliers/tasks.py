from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count

from .models import PurchaseOrder, SupplierDocument, Supplier, SupplierPerformanceMetric, SupplierRating
from .signals import (
    send_overdue_order_alert, 
    send_document_expiry_alert,
    calculate_supplier_performance_metrics
)
from datetime import timedelta
User = get_user_model()

@shared_task
def check_overdue_orders():
    """فحص أوامر الشراء المتأخرة - مهمة يومية"""
    try:
        overdue_orders = PurchaseOrder.objects.filter(
            status__in=['pending', 'approved', 'in_delivery'],
            expected_delivery_date__lt=timezone.now().date()
        )
        
        for order in overdue_orders:
            send_overdue_order_alert(order)
            
        return f"تم فحص {overdue_orders.count()} أمر شراء متأخر"
    except Exception as e:
        return f"خطأ في فحص الأوامر المتأخرة: {str(e)}"

@shared_task
def check_documents_expiry():
    """فحص انتهاء صلاحية مستندات الموردين - مهمة يومية"""
    try:
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
            
        return f"تم فحص {expiring_docs.count() + expired_docs.count()} مستند"
    except Exception as e:
        return f"خطأ في فحص المستندات: {str(e)}"

@shared_task
def calculate_monthly_performance():
    """حساب مقاييس أداء الموردين - مهمة شهرية"""
    try:
        today = timezone.now().date()
        last_month_start = today.replace(day=1) - datetime.timedelta(days=1)
        last_month_start = last_month_start.replace(day=1)
        last_month_end = today.replace(day=1) - datetime.timedelta(days=1)
        
        suppliers = Supplier.objects.filter(is_active=True)
        calculated_count = 0
        
        for supplier in suppliers:
            metric, created = SupplierPerformanceMetric.objects.get_or_create(
                supplier=supplier,
                period_start=last_month_start,
                period_end=last_month_end
            )
            metric.calculate_metrics()
            calculated_count += 1
            
        return f"تم حساب مقاييس الأداء لـ {calculated_count} مورد"
    except Exception as e:
        return f"خطأ في حساب مقاييس الأداء: {str(e)}"

@shared_task
def send_weekly_supplier_report():
    """إرسال تقرير أسبوعي عن الموردين"""
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        # جمع البيانات
        total_suppliers = Supplier.objects.filter(is_active=True).count()
        pending_orders = PurchaseOrder.objects.filter(
            status__in=['pending', 'approved', 'in_delivery']
        ).count()
        overdue_orders = PurchaseOrder.objects.filter(
            status__in=['pending', 'approved', 'in_delivery'],
            expected_delivery_date__lt=timezone.now().date()
        ).count()
        
        # الموردين ذوي التقييم المنخفض
        low_rated_suppliers = Supplier.objects.filter(
            is_active=True,
            current_rating__lt=3.0
        ).count()
        
        # إنشاء التقرير
        subject = "التقرير الأسبوعي للموردين"
        message = f"""
        التقرير الأسبوعي لإدارة الموردين
        
        إحصائيات عامة:
        - إجمالي الموردين النشطين: {total_suppliers}
        - أوامر الشراء المعلقة: {pending_orders}
        - أوامر الشراء المتأخرة: {overdue_orders}
        - موردين بتقييم منخفض: {low_rated_suppliers}
        
        تاريخ التقرير: {timezone.now().strftime('%Y-%m-%d')}
        """
        
        # إرسال للمدراء
        managers = User.objects.filter(
            role__in=['admin', 'manager']
        ).values_list('email', flat=True)
        
        if managers:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(managers),
                fail_silently=True
            )
            
        return "تم إرسال التقرير الأسبوعي"
    except Exception as e:
        return f"خطأ في إرسال التقرير: {str(e)}"

@shared_task
def cleanup_old_data():
    """تنظيف البيانات القديمة - مهمة شهرية"""
    try:
        # حذف مقاييس الأداء الأقدم من سنة
        old_date = timezone.now().date() - datetime.timedelta(days=365)
        deleted_metrics = SupplierPerformanceMetric.objects.filter(
            period_end__lt=old_date
        ).delete()
        
        return f"تم حذف {deleted_metrics[0]} مقياس أداء قديم"
    except Exception as e:
        return f"خطأ في تنظيف البيانات: {str(e)}"
    


@shared_task
def calculate_supplier_performance_metrics():
    """حساب مقاييس أداء الموردين"""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)  # آخر 30 يوم
    
    suppliers = Supplier.objects.filter(is_active=True)
    
    for supplier in suppliers:
        # Get or create performance metric
        metric, created = SupplierPerformanceMetric.objects.get_or_create(
            supplier=supplier,
            period_start=start_date,
            period_end=end_date,
            defaults={
                'total_orders': 0,
                'completed_orders': 0,
                'on_time_deliveries': 0,
                'total_amount': 0,
                'completion_rate': 0,
                'on_time_delivery_rate': 0,
                'average_rating': 0
            }
        )
        
        # Calculate metrics
        metric.calculate_metrics()
    
    return f"Performance metrics calculated for {suppliers.count()} suppliers"

@shared_task
def send_rating_reminders():
    """إرسال تذكيرات التقييم للأوامر المكتملة"""
    from .models import PurchaseOrder
    
    # Get completed orders from last 7 days without ratings
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)
    
    orders_without_ratings = PurchaseOrder.objects.filter(
        status='completed',
        actual_delivery_date__range=[start_date, end_date],
        ratings__isnull=True
    ).select_related('supplier', 'created_by')
    
    reminder_count = 0
    
    for order in orders_without_ratings:
        # Here you can implement email/notification sending
        # For now, we'll just log it
        print(f"Reminder needed for order {order.po_number} - {order.supplier.name}")
        reminder_count += 1
    
    return f"Rating reminders sent for {reminder_count} orders"

@shared_task
def update_all_supplier_ratings():
    """تحديث تقييمات جميع الموردين"""
    suppliers = Supplier.objects.all()
    updated_count = 0
    
    for supplier in suppliers:
        avg_rating = supplier.ratings.aggregate(
            avg=Avg('overall_rating')
        )['avg']
        
        new_rating = round(avg_rating, 2) if avg_rating else 0
        
        if supplier.current_rating != new_rating:
            supplier.current_rating = new_rating
            supplier.save(update_fields=['current_rating'])
            updated_count += 1
    
    return f"Updated ratings for {updated_count} suppliers"

@shared_task
def generate_rating_analytics():
    """إنشاء تحليلات التقييمات"""
    from django.db.models import Q
    
    # Overall statistics
    total_ratings = SupplierRating.objects.count()
    avg_overall_rating = SupplierRating.objects.aggregate(
        avg=Avg('overall_rating')
    )['avg'] or 0
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        count = SupplierRating.objects.filter(
            overall_rating__gte=i,
            overall_rating__lt=i+1
        ).count()
        rating_distribution[f"{i}_stars"] = count
    
    # Top rated suppliers
    top_suppliers = Supplier.objects.filter(
        current_rating__gt=0
    ).order_by('-current_rating')[:10]
    
    # Suppliers needing attention (low ratings)
    low_rated_suppliers = Supplier.objects.filter(
        current_rating__lt=3,
        current_rating__gt=0
    ).order_by('current_rating')[:10]
    
    analytics_data = {
        'total_ratings': total_ratings,
        'average_rating': round(avg_overall_rating, 2),
        'rating_distribution': rating_distribution,
        'top_suppliers': [
            {
                'id': s.id,
                'name': s.name,
                'rating': float(s.current_rating)
            } for s in top_suppliers
        ],
        'low_rated_suppliers': [
            {
                'id': s.id,
                'name': s.name,
                'rating': float(s.current_rating)
            } for s in low_rated_suppliers
        ],
        'generated_at': timezone.now().isoformat()
    }
    
    # You can save this to cache or database
    from django.core.cache import cache
    cache.set('supplier_rating_analytics', analytics_data, 3600)  # Cache for 1 hour
    
    return f"Analytics generated with {total_ratings} total ratings"