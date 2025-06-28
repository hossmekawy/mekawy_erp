from django.db.models import Avg, Sum, Count, Q
from django.utils import timezone
from decimal import Decimal
import datetime
from .models import Supplier, PurchaseOrder, SupplierRating, SupplierPerformanceMetric

def get_supplier_statistics():
    """الحصول على إحصائيات الموردين"""
    stats = {
        'total_suppliers': Supplier.objects.filter(is_active=True).count(),
        'total_purchase_orders': PurchaseOrder.objects.count(),
        'pending_orders': PurchaseOrder.objects.filter(
            status__in=['pending', 'approved', 'in_delivery']
        ).count(),
        'completed_orders': PurchaseOrder.objects.filter(status='completed').count(),
        'overdue_orders': PurchaseOrder.objects.filter(
            status__in=['pending', 'approved', 'in_delivery'],
            expected_delivery_date__lt=timezone.now().date()
        ).count(),
        'total_purchase_value': PurchaseOrder.objects.filter(
            status='completed'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
        'average_supplier_rating': Supplier.objects.filter(
            is_active=True
        ).aggregate(avg=Avg('current_rating'))['avg'] or Decimal('0'),
        'low_rated_suppliers': Supplier.objects.filter(
            is_active=True,
            current_rating__lt=3.0
        ).count(),
    }
    return stats

def get_top_suppliers(limit=10):
    """الحصول على أفضل الموردين"""
    return Supplier.objects.filter(
        is_active=True
    ).annotate(
        total_orders=Count('purchase_orders'),
        total_value=Sum('purchase_orders__total_amount')
    ).order_by('-current_rating', '-total_value')[:limit]

def get_supplier_performance_summary(supplier_id, months=12):
    """ملخص أداء مورد محدد"""
    supplier = Supplier.objects.get(id=supplier_id)
    end_date = timezone.now().date()
    start_date = end_date - datetime.timedelta(days=months * 30)
    
    orders = supplier.purchase_orders.filter(
        order_date__date__range=[start_date, end_date]
    )
    
    performance = {
        'supplier': supplier,
        'period_start': start_date,
        'period_end': end_date,
        'total_orders': orders.count(),
        'completed_orders': orders.filter(status='completed').count(),
        'total_value': orders.filter(status='completed').aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0'),
        'on_time_deliveries': orders.filter(
            status='completed',
            actual_delivery_date__lte=F('expected_delivery_date')
        ).count(),
        'average_rating': supplier.ratings.filter(
            rating_date__date__range=[start_date, end_date]
        ).aggregate(avg=Avg('overall_rating'))['avg'] or Decimal('0'),
    }
    
    # حساب النسب المئوية
    if performance['total_orders'] > 0:
        performance['completion_rate'] = (
            performance['completed_orders'] / performance['total_orders']
        ) * 100
        performance['on_time_rate'] = (
            performance['on_time_deliveries'] / performance['total_orders']
        ) * 100
    else:
        performance['completion_rate'] = 0
        performance['on_time_rate'] = 0
    
    return performance

def calculate_supplier_score(supplier):
    """حساب نقاط المورد الإجمالية"""
    # الحصول على آخر 6 أشهر من البيانات
    end_date = timezone.now().date()
    start_date = end_date - datetime.timedelta(days=180)
    
    orders = supplier.purchase_orders.filter(
        order_date__date__range=[start_date, end_date]
    )
    
    if not orders.exists():
        return 0
    
    # المعايير والأوزان
    weights = {
        'rating': 0.3,      # 30% للتقييم
        'completion': 0.25,  # 25% لمعدل الإكمال
        'on_time': 0.25,     # 25% للتسليم في الوقت
        'volume': 0.2,       # 20% لحجم التعامل
    }
    
    # حساب المعايير
    total_orders = orders.count()
    completed_orders = orders.filter(status='completed').count()
    on_time_orders = orders.filter(
        status='completed',
        actual_delivery_date__lte=F('expected_delivery_date')
    ).count()
    
    completion_rate = (completed_orders / total_orders) if total_orders > 0 else 0
    on_time_rate = (on_time_orders / total_orders) if total_orders > 0 else 0
    
    # تطبيع حجم التعامل (من 0 إلى 1)
    max_orders = PurchaseOrder.objects.filter(
        order_date__date__range=[start_date, end_date]
    ).values('supplier').annotate(
        order_count=Count('id')
    ).aggregate(max_count=Max('order_count'))['max_count'] or 1
    
    volume_score = min(total_orders / max_orders, 1.0)
    
    # حساب النقاط الإجمالية (من 0 إلى 100)
    total_score = (
        (supplier.current_rating / 5) * weights['rating'] * 100 +
        completion_rate * weights['completion'] * 100 +
        on_time_rate * weights['on_time'] * 100 +
        volume_score * weights['volume'] * 100
    )
    
    return round(total_score, 2)

def get_purchase_order_analytics(days=30):
    """تحليلات أوامر الشراء"""
    end_date = timezone.now().date()
    start_date = end_date - datetime.timedelta(days=days)
    
    orders = PurchaseOrder.objects.filter(
        order_date__date__range=[start_date, end_date]
    )
    
    analytics = {
        'total_orders': orders.count(),
        'total_value': orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
        'status_breakdown': {},
        'supplier_breakdown': {},
        'daily_orders': {},
    }
    
    # تحليل حسب الحالة
    for status, _ in PurchaseOrder.STATUS_CHOICES:
        count = orders.filter(status=status).count()
        if count > 0:
            analytics['status_breakdown'][status] = count
    
    # تحليل حسب المورد (أفضل 10)
    supplier_data = orders.values('supplier__name').annotate(
        order_count=Count('id'),
        total_value=Sum('total_amount')
    ).order_by('-total_value')[:10]
    
    for item in supplier_data:
        analytics['supplier_breakdown'][item['supplier__name']] = {
            'orders': item['order_count'],
            'value': item['total_value']
        }
    
    # تحليل يومي
    daily_data = orders.extra(
        select={'day': 'date(order_date)'}
    ).values('day').annotate(
        order_count=Count('id'),
        total_value=Sum('total_amount')
    ).order_by('day')
    
    for item in daily_data:
        analytics['daily_orders'][str(item['day'])] = {
            'orders': item['order_count'],
            'value': item['total_value']
        }
    
    return analytics

def recommend_suppliers(product_type=None, min_rating=3.0, limit=5):
    """اقتراح أفضل الموردين"""
    suppliers = Supplier.objects.filter(
        is_active=True,
        current_rating__gte=min_rating
    )
    
    if product_type:
        suppliers = suppliers.filter(supplier_type=product_type)
    
    # ترتيب حسب النقاط المحسوبة
    supplier_scores = []
    for supplier in suppliers:
        score = calculate_supplier_score(supplier)
        supplier_scores.append((supplier, score))
    
    # ترتيب تنازلي حسب النقاط
    supplier_scores.sort(key=lambda x: x[1], reverse=True)
    
    return supplier_scores[:limit]

def export_supplier_data(supplier_ids=None, format='csv'):
    """تصدير بيانات الموردين"""
    import csv
    import io
    
    suppliers = Supplier.objects.filter(is_active=True)
    if supplier_ids:
        suppliers = suppliers.filter(id__in=supplier_ids)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # كتابة العناوين
    headers = [
        'الكود', 'الاسم', 'النوع', 'الهاتف', 'البريد الإلكتروني',
        'التقييم الحالي', 'إجمالي المشتريات', 'عدد الأوامر',
        'تاريخ الإنشاء'
    ]
    writer.writerow(headers)
    
    # كتابة البيانات
    for supplier in suppliers:
        row = [
            supplier.code,
            supplier.name,
            supplier.get_supplier_type_display(),
            supplier.phone,
            supplier.email,
            supplier.current_rating,
            supplier.total_purchases,
            supplier.purchase_orders.count(),
            supplier.created_at.strftime('%Y-%m-%d')
        ]
        writer.writerow(row)
    
    return output.getvalue()


def get_supplier_rating_analytics():
    """Get comprehensive supplier rating analytics"""
    
    # Overall statistics
    total_suppliers = Supplier.objects.filter(is_active=True).count()
    rated_suppliers = Supplier.objects.filter(
        is_active=True, 
        current_rating__gt=0
    ).count()
    
    total_ratings = SupplierRating.objects.count()
    avg_rating = SupplierRating.objects.aggregate(
        avg=Avg('overall_rating')
    )['avg'] or 0
    
    # Rating distribution
    rating_ranges = [
        (4.5, 5.0, 'ممتاز'),
        (3.5, 4.5, 'جيد جداً'),
        (2.5, 3.5, 'جيد'),
        (1.5, 2.5, 'مقبول'),
        (0, 1.5, 'ضعيف')
    ]
    
    distribution = []
    for min_rating, max_rating, label in rating_ranges:
        count = Supplier.objects.filter(
            current_rating__gte=min_rating,
            current_rating__lt=max_rating,
            is_active=True
        ).count()
        distribution.append({
            'range': f'{min_rating}-{max_rating}',
            'label': label,
            'count': count,
            'percentage': (count / rated_suppliers * 100) if rated_suppliers > 0 else 0
        })
    
    # Top and bottom performers
    top_suppliers = Supplier.objects.filter(
        is_active=True,
        current_rating__gt=0
    ).order_by('-current_rating')[:10]
    
    bottom_suppliers = Supplier.objects.filter(
        is_active=True,
        current_rating__gt=0
    ).order_by('current_rating')[:5]
    
    # Recent trends (last 6 months)
    six_months_ago = timezone.now().date() - timedelta(days=180)
    recent_ratings = SupplierRating.objects.filter(
        rating_date__date__gte=six_months_ago
    ).order_by('rating_date')
    
    # Monthly trend
    monthly_trends = {}
    for rating in recent_ratings:
        month_key = rating.rating_date.strftime('%Y-%m')
        if month_key not in monthly_trends:
            monthly_trends[month_key] = []
        monthly_trends[month_key].append(rating.overall_rating)
    
    trend_data = []
    for month, ratings in monthly_trends.items():
        avg_monthly_rating = sum(ratings) / len(ratings)
        trend_data.append({
            'month': month,
            'average_rating': round(avg_monthly_rating, 2),
            'count': len(ratings)
        })
    
    return {
        'overview': {
            'total_suppliers': total_suppliers,
            'rated_suppliers': rated_suppliers,
            'unrated_suppliers': total_suppliers - rated_suppliers,
            'total_ratings': total_ratings,
            'average_rating': round(avg_rating, 2)
        },
        'distribution': distribution,
        'top_performers': [
            {
                'id': s.id,
                'name': s.name,
                'rating': float(s.current_rating),
                'rating_count': s.ratings.count()
            } for s in top_suppliers
        ],
        'bottom_performers': [
            {
                'id': s.id,
                'name': s.name,
                'rating': float(s.current_rating),
                'rating_count': s.ratings.count()
            } for s in bottom_suppliers
        ],
        'monthly_trends': sorted(trend_data, key=lambda x: x['month'])
    }

def calculate_supplier_score(supplier):
    """Calculate comprehensive supplier score"""
    
    # Base rating (40% weight)
    rating_score = (supplier.current_rating / 5) * 40
    
    # Performance metrics (30% weight)
    latest_metric = supplier.performance_metrics.order_by('-period_end').first()
    if latest_metric:
        performance_score = (
            (latest_metric.completion_rate / 100) * 15 +
            (latest_metric.on_time_delivery_rate / 100) * 15
        )
    else:
        performance_score = 0
    
    # Order volume (20% weight) - normalized
    total_amount = float(supplier.total_purchases)
    max_amount = Supplier.objects.aggregate(
        max_amount=models.Max('purchase_orders__total_amount')
    )['max_amount'] or 1
    volume_score = (total_amount / max_amount) * 20
    
    # Consistency (10% weight) - based on rating variance
    ratings = supplier.ratings.values_list('overall_rating', flat=True)
    if len(ratings) > 1:
        import statistics
        variance = statistics.variance(ratings)
        consistency_score = max(0, (1 - variance) * 10)
    else:
        consistency_score = 5  # Neutral score for single/no ratings
    
    total_score = rating_score + performance_score + volume_score + consistency_score
    
    return {
        'total_score': round(total_score, 2),
        'breakdown': {
            'rating': round(rating_score, 2),
            'performance': round(performance_score, 2),
            'volume': round(volume_score, 2),
            'consistency': round(consistency_score, 2)
        },
        'grade': get_score_grade(total_score)
    }

def get_score_grade(score):
    """Convert score to letter grade"""
    if score >= 90:
        return 'A+'
    elif score >= 85:
        return 'A'
    elif score >= 80:
        return 'A-'
    elif score >= 75:
        return 'B+'
    elif score >= 70:
        return 'B'
    elif score >= 65:
        return 'B-'
    elif score >= 60:
        return 'C+'
    elif score >= 55:
        return 'C'
    elif score >= 50:
        return 'C-'
    else:
        return 'D'
    
def get_rating_recommendations(supplier):
    """Get recommendations based on supplier ratings"""
    
    recommendations = []
    rating_summary = supplier.get_rating_summary()
    
    if rating_summary['total_ratings'] == 0:
        recommendations.append({
            'type': 'info',
            'message': 'لا توجد تقييمات لهذا المورد بعد',
            'action': 'قم بإضافة تقييم بعد إكمال أول طلبية'
        })
        return recommendations
    
    avg_rating = rating_summary['average_rating']
    criteria = rating_summary['criteria_averages']
    
    # Overall rating recommendations
    if avg_rating < 2.5:
        recommendations.append({
            'type': 'danger',
            'message': 'التقييم العام منخفض جداً',
            'action': 'يُنصح بمراجعة التعامل مع هذا المورد أو البحث عن بديل'
        })
    elif avg_rating < 3.5:
        recommendations.append({
            'type': 'warning',
            'message': 'التقييم العام يحتاج تحسين',
            'action': 'ناقش نقاط الضعف مع المورد ووضع خطة للتحسين'
        })
    elif avg_rating >= 4.5:
        recommendations.append({
            'type': 'success',
            'message': 'مورد ممتاز',
            'action': 'يمكن الاعتماد عليه في الطلبيات المهمة'
        })
    
    # Specific criteria recommendations
    weak_areas = []
    strong_areas = []
    
    criteria_labels = {
        'quality': 'الجودة',
        'delivery': 'التسليم',
        'price': 'السعر',
        'service': 'الخدمة',
        'communication': 'التواصل'
    }
    
    for criterion, avg_score in criteria.items():
        if avg_score < 3.0:
            weak_areas.append(criteria_labels[criterion])
        elif avg_score >= 4.5:
            strong_areas.append(criteria_labels[criterion])
    
    if weak_areas:
        recommendations.append({
            'type': 'warning',
            'message': f'نقاط ضعف في: {", ".join(weak_areas)}',
            'action': 'ركز على تحسين هذه المجالات في المفاوضات القادمة'
        })
    
    if strong_areas:
        recommendations.append({
            'type': 'success',
            'message': f'نقاط قوة في: {", ".join(strong_areas)}',
            'action': 'استفد من هذه المميزات في التخطيط المستقبلي'
        })
    
    # Rating consistency check
    ratings = list(supplier.ratings.values_list('overall_rating', flat=True))
    if len(ratings) > 3:
        import statistics
        variance = statistics.variance(ratings)
        if variance > 1.5:
            recommendations.append({
                'type': 'info',
                'message': 'التقييمات متذبذبة',
                'action': 'راقب الأداء عن كثب لضمان الاستقرار'
            })
    
    # Recent performance trend
    recent_ratings = supplier.ratings.order_by('-rating_date')[:5]
    if len(recent_ratings) >= 3:
        recent_avg = sum(r.overall_rating for r in recent_ratings[:3]) / 3
        older_avg = sum(r.overall_rating for r in recent_ratings[3:]) / len(recent_ratings[3:])
        
        if recent_avg > older_avg + 0.5:
            recommendations.append({
                'type': 'success',
                'message': 'تحسن في الأداء مؤخراً',
                'action': 'استمر في التعاون وشجع هذا التحسن'
            })
        elif recent_avg < older_avg - 0.5:
            recommendations.append({
                'type': 'warning',
                'message': 'تراجع في الأداء مؤخراً',
                'action': 'تواصل مع المورد لمعرفة أسباب التراجع'
            })
    
    return recommendations

def export_supplier_ratings_report(supplier_ids=None, date_from=None, date_to=None):
    """Export supplier ratings report"""
    import csv
    from io import StringIO
    from django.utils.encoding import smart_str
    
    # Build queryset
    ratings = SupplierRating.objects.select_related(
        'supplier', 'purchase_order', 'rated_by'
    )
    
    if supplier_ids:
        ratings = ratings.filter(supplier_id__in=supplier_ids)
    
    if date_from:
        ratings = ratings.filter(rating_date__date__gte=date_from)
    
    if date_to:
        ratings = ratings.filter(rating_date__date__lte=date_to)
    
    ratings = ratings.order_by('-rating_date')
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        'المورد', 'رقم أمر الشراء', 'التقييم العام', 'تقييم الجودة',
        'تقييم التسليم', 'تقييم السعر', 'تقييم الخدمة', 'تقييم التواصل',
        'التعليقات', 'الموسم', 'المقيم', 'تاريخ التقييم'
    ])
    
    # Data rows
    for rating in ratings:
        writer.writerow([
            smart_str(rating.supplier.name),
            smart_str(rating.purchase_order.po_number if rating.purchase_order else 'غير محدد'),
            smart_str(rating.overall_rating),
            smart_str(rating.quality_rating),
            smart_str(rating.delivery_rating),
            smart_str(rating.price_rating),
            smart_str(rating.service_rating),
            smart_str(rating.communication_rating),
            smart_str(rating.comments or ''),
            smart_str(rating.season or ''),
            smart_str(rating.rated_by.username if rating.rated_by else ''),
            smart_str(rating.rating_date.strftime('%Y-%m-%d %H:%M')),
        ])
    
    return output.getvalue()

def bulk_calculate_supplier_scores():
    """Calculate scores for all active suppliers"""
    suppliers = Supplier.objects.filter(is_active=True)
    scores = {}
    
    for supplier in suppliers:
        scores[supplier.id] = calculate_supplier_score(supplier)
    
    return scores

def get_supplier_comparison(supplier_ids):
    """Compare multiple suppliers"""
    suppliers = Supplier.objects.filter(
        id__in=supplier_ids,
        is_active=True
    ).prefetch_related('ratings')
    
    comparison_data = []
    
    for supplier in suppliers:
        rating_summary = supplier.get_rating_summary()
        score_data = calculate_supplier_score(supplier)
        
        comparison_data.append({
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'type': supplier.get_supplier_type_display()
            },
            'ratings': rating_summary,
            'score': score_data,
            'performance': {
                'total_orders': supplier.purchase_orders.count(),
                'completed_orders': supplier.purchase_orders.filter(status='completed').count(),
                'total_amount': float(supplier.total_purchases),
                'pending_amount': float(supplier.pending_amount)
            }
        })
    
    return comparison_data

def suggest_suppliers_for_rating():
    """Suggest suppliers that need rating based on completed orders"""
    from datetime import timedelta
    from django.utils import timezone
    
    # Get suppliers with completed orders in last 30 days but no recent ratings
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    suppliers_needing_rating = []
    
    # Find completed orders without ratings
    completed_orders = PurchaseOrder.objects.filter(
        status='completed',
        actual_delivery_date__gte=thirty_days_ago,
        ratings__isnull=True
    ).select_related('supplier').distinct()
    
    for order in completed_orders:
        suppliers_needing_rating.append({
            'supplier': order.supplier,
            'order': order,
            'days_since_completion': (timezone.now().date() - order.actual_delivery_date).days,
            'priority': 'high' if (timezone.now().date() - order.actual_delivery_date).days > 14 else 'medium'
        })
    
    # Sort by priority and days since completion
    suppliers_needing_rating.sort(
        key=lambda x: (x['priority'] == 'high', x['days_since_completion']),
        reverse=True
    )
    
    return suppliers_needing_rating

def validate_rating_data(rating_data):
    """Validate rating data before saving"""
    errors = []
    
    required_fields = ['quality_rating', 'delivery_rating', 'price_rating', 
                      'service_rating', 'communication_rating']
    
    for field in required_fields:
        value = rating_data.get(field)
        if not value:
            errors.append(f'{field} مطلوب')
        elif not isinstance(value, int) or value < 1 or value > 5:
            errors.append(f'{field} يجب أن يكون رقم بين 1 و 5')
    
    # Check if supplier exists
    supplier_id = rating_data.get('supplier_id')
    if supplier_id:
        try:
            Supplier.objects.get(id=supplier_id, is_active=True)
        except Supplier.DoesNotExist:
            errors.append('المورد غير موجود أو غير نشط')
    
    # Check if purchase order exists (if provided)
    purchase_order_id = rating_data.get('purchase_order_id')
    if purchase_order_id:
        try:
            order = PurchaseOrder.objects.get(id=purchase_order_id)
            if order.status != 'completed':
                errors.append('لا يمكن تقييم أمر غير مكتمل')
        except PurchaseOrder.DoesNotExist:
            errors.append('أمر الشراء غير موجود')
    
    return errors
