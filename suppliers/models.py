from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
from django.db.models import F,Sum


User = get_user_model()

class Supplier(models.Model):
    """نموذج الموردين"""
    SUPPLIER_TYPES = [
        ('fabric', 'مورد أقمشة'),
        ('thread', 'مورد خيوط'),
        ('accessories', 'مورد إكسسوارات'),
        ('mixed', 'مورد متنوع'),
    ]
    
    PAYMENT_METHODS = [
        ('smart_wallet', 'Smart Wallet'),
        ('instapay', 'InstaPay'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cash', 'كاش'),
    ]
    
    # البيانات الأساسية
    name = models.CharField(max_length=200, verbose_name="اسم المورد")
    code = models.CharField(max_length=50, unique=True, verbose_name="كود المورد")
    supplier_type = models.CharField(max_length=20, choices=SUPPLIER_TYPES, verbose_name="نوع المورد")
    
    # بيانات الاتصال
    contact_person = models.CharField(max_length=100, verbose_name="الشخص المسؤول")
    phone = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    address = models.TextField(verbose_name="العنوان")
    
    # بيانات الحساب المصرفي
    bank_name = models.CharField(max_length=100, blank=True, verbose_name="اسم البنك")
    account_number = models.CharField(max_length=50, blank=True, verbose_name="رقم الحساب")
    account_holder_name = models.CharField(max_length=100, blank=True, verbose_name="اسم صاحب الحساب")
    # Add these fields after the existing payment fields
    smart_wallet_phone = models.CharField(max_length=20, blank=True, verbose_name="رقم Smart Wallet")
    instapay_identifier = models.CharField(max_length=100, blank=True, verbose_name="معرف InstaPay")

    
    # طرق الدفع المدعومة
    supported_payment_methods = models.JSONField(default=list, verbose_name="طرق الدفع المدعومة")
    
    # معلومات إضافية
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="حد الائتمان")
    payment_terms_days = models.PositiveIntegerField(default=30, verbose_name="مدة السداد بالأيام")
    
    # الحالة والتقييم
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    current_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name="التقييم الحالي"
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تعديل")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="أنشأ بواسطة")
    
    class Meta:
        verbose_name = "مورد"
        verbose_name_plural = "الموردين"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def total_purchases(self):
        """إجمالي المشتريات"""
        return self.purchase_orders.filter(status='completed').aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')
    
    @property
    def pending_amount(self):
        """المبلغ المعلق"""
        return self.purchase_orders.filter(
            status__in=['pending', 'in_delivery']
        ).aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')
# Add these methods to the Supplier model class

    def get_rating_summary(self):
        """ملخص التقييمات"""
        ratings = self.ratings.all()
        if not ratings.exists():
            return {
                'total_ratings': 0,
                'average_rating': 0,
                'criteria_averages': {
                    'quality': 0, 'delivery': 0, 'price': 0,
                    'service': 0, 'communication': 0
                },
                'rating_distribution': {str(i): 0 for i in range(1, 6)}
            }
        
        # Calculate averages
        criteria_averages = {
            'quality': ratings.aggregate(avg=Avg('quality_rating'))['avg'] or 0,
            'delivery': ratings.aggregate(avg=Avg('delivery_rating'))['avg'] or 0,
            'price': ratings.aggregate(avg=Avg('price_rating'))['avg'] or 0,
            'service': ratings.aggregate(avg=Avg('service_rating'))['avg'] or 0,
            'communication': ratings.aggregate(avg=Avg('communication_rating'))['avg'] or 0,
        }
        
        # Rating distribution
        rating_distribution = {}
        for i in range(1, 6):
            count = ratings.filter(
                overall_rating__gte=i, 
                overall_rating__lt=i+1
            ).count()
            rating_distribution[str(i)] = count
        
        return {
            'total_ratings': ratings.count(),
            'average_rating': float(self.current_rating),
            'criteria_averages': {k: float(v) for k, v in criteria_averages.items()},
            'rating_distribution': rating_distribution
        }
    
    def get_recent_ratings(self, limit=5):
        """أحدث التقييمات"""
        return self.ratings.select_related(
            'purchase_order', 'rated_by'
        ).order_by('-rating_date')[:limit]
    
    def can_be_rated_by(self, user):
        """هل يمكن للمستخدم تقييم هذا المورد"""
        # Check if user has completed orders with this supplier
        return self.purchase_orders.filter(
            status='completed',
            created_by=user
        ).exists()
    
    def get_rating_trend(self, months=6):
        """اتجاه التقييم خلال فترة معينة"""
        from django.utils import timezone
        from datetime import timedelta
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=months * 30)
        
        ratings = self.ratings.filter(
            rating_date__date__range=[start_date, end_date]
        ).order_by('rating_date')
        
        if not ratings.exists():
            return []
        
        # Group by month
        monthly_ratings = {}
        for rating in ratings:
            month_key = rating.rating_date.strftime('%Y-%m')
            if month_key not in monthly_ratings:
                monthly_ratings[month_key] = []
            monthly_ratings[month_key].append(rating.overall_rating)
        
        # Calculate monthly averages
        trend_data = []
        for month, ratings_list in monthly_ratings.items():
            avg_rating = sum(ratings_list) / len(ratings_list)
            trend_data.append({
                'month': month,
                'average_rating': round(avg_rating, 2),
                'count': len(ratings_list)
            })
        
        return trend_data

# Add these methods to the SupplierRating model class

    def get_rating_color(self):
        """لون التقييم حسب القيمة"""
        if self.overall_rating >= 4.5:
            return 'success'
        elif self.overall_rating >= 3.5:
            return 'warning'
        elif self.overall_rating >= 2.5:
            return 'info'
        else:
            return 'danger'
    
    def get_rating_text(self):
        """نص التقييم"""
        if self.overall_rating >= 4.5:
            return 'ممتاز'
        elif self.overall_rating >= 3.5:
            return 'جيد جداً'
        elif self.overall_rating >= 2.5:
            return 'جيد'
        elif self.overall_rating >= 1.5:
            return 'مقبول'
        else:
            return 'ضعيف'
    
    def get_criteria_breakdown(self):
        """تفصيل المعايير"""
        return {
            'quality': {
                'value': self.quality_rating,
                'label': 'الجودة',
                'percentage': (self.quality_rating / 5) * 100
            },
            'delivery': {
                'value': self.delivery_rating,
                'label': 'التسليم',
                'percentage': (self.delivery_rating / 5) * 100
            },
            'price': {
                'value': self.price_rating,
                'label': 'السعر',
                'percentage': (self.price_rating / 5) * 100
            },
            'service': {
                'value': self.service_rating,
                'label': 'الخدمة',
                'percentage': (self.service_rating / 5) * 100
            },
            'communication': {
                'value': self.communication_rating,
                'label': 'التواصل',
                'percentage': (self.communication_rating / 5) * 100
            }
        }



class PurchaseOrder(models.Model):
    """أوامر الشراء"""
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('pending', 'معلق'),
        ('approved', 'موافق عليه'),
        ('in_delivery', 'قيد التسليم'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'منخفض'),
        ('medium', 'متوسط'),
        ('high', 'عالي'),
        ('urgent', 'عاجل'),
    ]
    
    # البيانات الأساسية
    po_number = models.CharField(max_length=50, unique=True, verbose_name="رقم أمر الشراء")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders', verbose_name="المورد")
    
    # التواريخ
    order_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الأمر")
    expected_delivery_date = models.DateField(verbose_name="تاريخ التسليم المتوقع")
    actual_delivery_date = models.DateField(null=True, blank=True, verbose_name="تاريخ التسليم الفعلي")
    
    # الحالة والأولوية
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="الحالة")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name="الأولوية")
    
    # المبالغ
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="المجموع الفرعي")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الضريبة")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الخصم")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="المبلغ الإجمالي")
    
    # معلومات إضافية
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    terms_conditions = models.TextField(blank=True, verbose_name="الشروط والأحكام")
    
    # المسؤولين
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_purchase_orders', verbose_name="أنشأ بواسطة")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_purchase_orders', verbose_name="وافق عليه")
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تعديل")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الموافقة")
    
    class Meta:
        verbose_name = "أمر شراء"
        verbose_name_plural = "أوامر الشراء"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"أمر شراء {self.po_number} - {self.supplier.name}"
    
    def calculate_totals(self):
        """حساب المبالغ الإجمالية"""
        subtotal = self.items.aggregate(
            total=Sum(F('quantity_ordered') * F('unit_price'))
        )['total'] or Decimal('0')
        
        self.subtotal = subtotal
        self.total_amount = subtotal + self.tax_amount - self.discount_amount
        self.save(update_fields=['subtotal', 'total_amount'])
        
    @property
    def is_overdue(self):
        """هل الأمر متأخر؟"""
        if self.status in ['completed', 'cancelled']:
            return False
        return timezone.now().date() > self.expected_delivery_date
    
    @property
    def days_overdue(self):
        """عدد أيام التأخير"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.expected_delivery_date).days
    
    @property
    def completion_percentage(self):
        """نسبة الإكمال"""
        total_items = self.items.count()
        if total_items == 0:
            return 0
        completed_items = self.items.filter(
            quantity_received__gte=F('quantity_ordered')
        ).count()
        return (completed_items / total_items) * 100

class PurchaseOrderItem(models.Model):
    """عناصر أمر الشراء"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items', verbose_name="أمر الشراء")
    product = models.ForeignKey('warehouses.Product', on_delete=models.CASCADE, verbose_name="المنتج")
    
    # الكميات والأسعار
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الكمية المطلوبة")
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="الكمية المستلمة")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="سعر الوحدة")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="السعر الإجمالي")
    
    # معلومات إضافية
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "عنصر أمر شراء"
        verbose_name_plural = "عناصر أوامر الشراء"
        unique_together = ['purchase_order', 'product']
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity_ordered} {self.product.unit}"
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)
    
    @property
    def quantity_pending(self):
        """الكمية المعلقة"""
        pending =  self.quantity_ordered - self.quantity_received
        return max(pending, Decimal('0'))  # Ensure it's never negative
    
    @property
    def is_fully_received(self):
        """هل تم استلام الكمية كاملة؟"""
        return self.quantity_received >= self.quantity_ordered

class Payment(models.Model):
    """سجل الدفعات"""
    PAYMENT_TYPES = [
        ('incoming', 'وارد'),
        ('outgoing', 'صادر'),
    ]
    
    PAYMENT_METHODS = [
        ('smart_wallet', 'Smart Wallet'),
        ('instapay', 'InstaPay'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cash', 'كاش'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'معلق'),
        ('completed', 'مكتمل'),
        ('failed', 'فاشل'),
        ('cancelled', 'ملغي'),
    ]
    
    # البيانات الأساسية
    payment_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الدفعة")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='payments', verbose_name="المورد")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name="أمر الشراء")
    
    
    # تفاصيل الدفعة
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES, verbose_name="نوع الدفعة")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, verbose_name="طريقة الدفع")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="المبلغ")
    
    # الحالة والتواريخ
    status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='pending', verbose_name="الحالة")
    payment_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الدفعة")
    due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستحقاق")
    
    # معلومات إضافية
    reference_number = models.CharField(max_length=100, blank=True, verbose_name="رقم المرجع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    # المسؤول
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="أنشأ بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"دفعة {self.payment_number} - {self.supplier.name} ({self.amount})"

class SupplierRating(models.Model):
    """تقييم الموردين"""
    RATING_CRITERIA = [
        ('quality', 'جودة المنتجات'),
        ('delivery', 'الالتزام بالتسليم'),
        ('price', 'تنافسية الأسعار'),
        ('service', 'خدمة العملاء'),
        ('communication', 'التواصل'),
    ]
    
    # البيانات الأساسية
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='ratings', verbose_name="المورد")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='ratings', verbose_name="أمر الشراء")
    
    # التقييمات
    quality_rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="تقييم الجودة")
    delivery_rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="تقييم التسليم")
    price_rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="تقييم السعر")
    service_rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="تقييم الخدمة")
    communication_rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="تقييم التواصل")
    
    # التقييم الإجمالي
    overall_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, verbose_name="التقييم الإجمالي")
    
    # معلومات إضافية
    comments = models.TextField(blank=True, verbose_name="تعليقات")
    season = models.CharField(max_length=50, blank=True, verbose_name="الموسم")
    
    # المسؤول والتواريخ
    rated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="قيم بواسطة")
    rating_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التقييم")
    
    class Meta:
        verbose_name = "تقييم مورد"
        verbose_name_plural = "تقييمات الموردين"
        ordering = ['-rating_date']
        unique_together = ['supplier', 'purchase_order']
    
    def __str__(self):
        return f"تقييم {self.supplier.name} - {self.overall_rating}/5"
    
    def save(self, *args, **kwargs):
        # حساب التقييم الإجمالي
        self.overall_rating = (
            self.quality_rating + 
            self.delivery_rating + 
            self.price_rating + 
            self.service_rating + 
            self.communication_rating
        ) / 5
        super().save(*args, **kwargs)

class SupplierContact(models.Model):
    """جهات اتصال المورد"""
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='contacts', verbose_name="المورد")
    name = models.CharField(max_length=100, verbose_name="الاسم")
    position = models.CharField(max_length=100, verbose_name="المنصب")
    phone = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    is_primary = models.BooleanField(default=False, verbose_name="جهة الاتصال الأساسية")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "جهة اتصال المورد"
        verbose_name_plural = "جهات اتصال الموردين"
    
    def __str__(self):
        return f"{self.name} - {self.supplier.name}"

class SupplierDocument(models.Model):
    """مستندات المورد"""
    DOCUMENT_TYPES = [
        ('contract', 'عقد'),
        ('certificate', 'شهادة'),
        ('license', 'ترخيص'),
        ('tax_card', 'بطاقة ضريبية'),
        ('commercial_register', 'سجل تجاري'),
        ('other', 'أخرى'),
    ]
    
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='documents', verbose_name="المورد")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, verbose_name="نوع المستند")
    title = models.CharField(max_length=200, verbose_name="عنوان المستند")
    file = models.FileField(upload_to='supplier_documents/', verbose_name="الملف")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="رفع بواسطة")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الرفع")
    
    class Meta:
        verbose_name = "مستند مورد"
        verbose_name_plural = "مستندات الموردين"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.supplier.name}"
    
    @property
    def is_expired(self):
        """هل المستند منتهي الصلاحية؟"""
        if not self.expiry_date:
            return False
        return timezone.now().date() > self.expiry_date
    
    @property
    def days_to_expiry(self):
        """عدد الأيام حتى انتهاء الصلاحية"""
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days

class PurchaseOrderDelivery(models.Model):
    """تسليم أوامر الشراء"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='deliveries', verbose_name="أمر الشراء")
    delivery_number = models.CharField(max_length=50, unique=True, verbose_name="رقم التسليم")
    
    # تفاصيل التسليم
    delivery_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ التسليم")
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="استلم بواسطة")
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.CASCADE, verbose_name="المخزن")
    
    # معلومات إضافية
    delivery_notes = models.TextField(blank=True, verbose_name="ملاحظات التسليم")
    quality_check_passed = models.BooleanField(default=True, verbose_name="اجتاز فحص الجودة")
    quality_notes = models.TextField(blank=True, verbose_name="ملاحظات الجودة")
    
    # الحالة
    is_complete = models.BooleanField(default=False, verbose_name="مكتمل")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "تسليم أمر شراء"
        verbose_name_plural = "تسليمات أوامر الشراء"
        ordering = ['-delivery_date']
    
    def __str__(self):
        return f"تسليم {self.delivery_number} - {self.purchase_order.po_number}"

class PurchaseOrderDeliveryItem(models.Model):
    """عناصر تسليم أمر الشراء"""
    delivery = models.ForeignKey(PurchaseOrderDelivery, on_delete=models.CASCADE, related_name='items', verbose_name="التسليم")
    purchase_order_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.CASCADE, verbose_name="عنصر أمر الشراء")
    quantity_delivered = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الكمية المسلمة")
    
    # فحص الجودة
    quality_approved = models.BooleanField(default=True, verbose_name="جودة معتمدة")
    quality_notes = models.TextField(blank=True, verbose_name="ملاحظات الجودة")
    
    class Meta:
        verbose_name = "عنصر تسليم أمر شراء"
        verbose_name_plural = "عناصر تسليمات أوامر الشراء"
    
    def __str__(self):
        return f"{self.purchase_order_item.product.name} - {self.quantity_delivered}"

class SupplierPerformanceMetric(models.Model):
    """مقاييس أداء المورد"""
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='performance_metrics', verbose_name="المورد")
    
    # الفترة الزمنية
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    
    # المقاييس
    total_orders = models.PositiveIntegerField(default=0, verbose_name="إجمالي الأوامر")
    completed_orders = models.PositiveIntegerField(default=0, verbose_name="الأوامر المكتملة")
    on_time_deliveries = models.PositiveIntegerField(default=0, verbose_name="التسليمات في الوقت")
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="إجمالي المبلغ")
    
    # النسب المئوية
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="معدل الإكمال")
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="معدل التسليم في الوقت")
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, verbose_name="متوسط التقييم")
    
    # التواريخ
    calculated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ الحساب")
    
    class Meta:
        verbose_name = "مقياس أداء المورد"
        verbose_name_plural = "مقاييس أداء الموردين"
        unique_together = ['supplier', 'period_start', 'period_end']
        ordering = ['-period_end']
    
    def __str__(self):
        return f"أداء {self.supplier.name} ({self.period_start} - {self.period_end})"
    
    def calculate_metrics(self):
        """حساب المقاييس"""
        orders = self.supplier.purchase_orders.filter(
            order_date__date__range=[self.period_start, self.period_end]
        )
        
        self.total_orders = orders.count()
        self.completed_orders = orders.filter(status='completed').count()
        self.on_time_deliveries = orders.filter(
            status='completed',
            actual_delivery_date__lte=models.F('expected_delivery_date')
        ).count()
        self.total_amount = orders.filter(status='completed').aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')
        
        # حساب النسب
        if self.total_orders > 0:
            self.completion_rate = (self.completed_orders / self.total_orders) * 100
            self.on_time_delivery_rate = (self.on_time_deliveries / self.total_orders) * 100
        
        # حساب متوسط التقييم
        ratings = self.supplier.ratings.filter(
            rating_date__date__range=[self.period_start, self.period_end]
        )
        if ratings.exists():
            self.average_rating = ratings.aggregate(
                avg=models.Avg('overall_rating')
            )['avg'] or Decimal('0')
        
        self.save()
