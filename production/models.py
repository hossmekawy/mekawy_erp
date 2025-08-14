# Django imports
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Sum, F, Q, Count, DecimalField
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType # FIX: This import was missing
# Standard library imports
import datetime
from decimal import Decimal

# Project imports
from warehouses.models import Product, StockItem as Stock, Warehouse

User = get_user_model()





class SizeGroup(models.Model):
    """Size Groups"""
    name = models.CharField(max_length=50, verbose_name="اسم مجموعة المقاسات")
    sizes = models.JSONField(default=list, verbose_name="المقاسات")  # ['30', '32', '34']
    
    class Meta:
        verbose_name = "مجموعة مقاسات"
        verbose_name_plural = "مجموعات المقاسات"
    
    def __str__(self):
        return f"{self.name} ({', '.join(self.sizes)})"


class BillOfMaterials(models.Model):
    """Represents the Bill of Materials (BOM) for a specific finished product."""
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='boms', 
        verbose_name="المنتج النهائي",
        limit_choices_to={'product_type': 'finished'} # Ensures only finished products can have a BOM
    )
    size_group = models.ForeignKey(
        SizeGroup, 
        on_delete=models.PROTECT, 
        related_name='boms', 
        verbose_name="مجموعة المقاسات", 
        null=True, 
        blank=True
    ) 
    version = models.PositiveIntegerField(default=1, verbose_name="الإصدار")
    is_active = models.BooleanField(default=True, verbose_name="الإصدار النشط")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='versions', verbose_name="الإصدار السابق")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="تم إنشاؤه بواسطة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "قائمة المواد"
        verbose_name_plural = "قوائم المواد"
        unique_together = ('product', 'size_group', 'version')
        ordering = ['-version']

    def __str__(self):
        return f"BOM for {self.product.name} ({self.size_group.name if self.size_group else 'Default'}) - v{self.version}"

    @property
    def total_cost(self):
        total = self.items.aggregate(
            total_cost=Sum(F('quantity') * F('material__cost_price'), output_field=models.DecimalField())
        )['total_cost']
        return total or 0


class BOMItem(models.Model):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='items', verbose_name="قائمة المواد")
    material = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='bom_items', verbose_name="المادة الخام")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))], verbose_name="الكمية")
    notes = models.CharField(max_length=255, blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "عنصر قائمة المواد"
        verbose_name_plural = "عناصر قائمة المواد"
        unique_together = ('bom', 'material')

    @property
    def cost(self):
        return self.quantity * self.material.cost_price

class ManufacturerProductPrice(models.Model):
    """
    Stores the specific price a manufacturer charges for a specific product.
    """
    manufacturer = models.ForeignKey('ExternalManufacturer', on_delete=models.CASCADE, related_name='product_prices', verbose_name="المصنع")
    product = models.ForeignKey(
        'warehouses.Product',
        on_delete=models.CASCADE,
        related_name='manufacturer_prices',
        limit_choices_to={'product_type': 'finished'},
        verbose_name="المنتج"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر القطعة")

    class Meta:
        verbose_name = "سعر منتج المصنع"
        verbose_name_plural = "أسعار منتجات المصنع"
        # Ensure a manufacturer can only have one price for a specific product
        unique_together = ('manufacturer', 'product')
        ordering = ['manufacturer', 'product__name']

    def __str__(self):
        return f"{self.manufacturer.name} - {self.product.name}: {self.price}"


class ProductionOrder(models.Model):
    """أوامر الإنتاج"""
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('approved', 'موافق عليه'),
        ('in_cutting', 'قيد القص'),
        ('in_assembly', 'قيد التجميع'),
        ('in_dyeing', 'قيد الصباغة'),
        ('in_finishing', 'قيد التشطيب'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'منخفض'),
        ('medium', 'متوسط'),
        ('high', 'عالي'),
        ('urgent', 'عاجل'),
    ]

    QUALITY_LEVELS = [
        ('standard', 'عادي'),
        ('premium', 'ممتاز'),
        ('luxury', 'فاخر'),
    ]
    
    order_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الأمر")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="المنتج" , limit_choices_to={'product_type': 'finished'})
    batch_number = models.CharField(max_length=100, verbose_name="رقم الدفعة")
    quantity_ordered = models.PositiveIntegerField(verbose_name="الكمية المطلوبة")
    textile_stock = models.ForeignKey(Stock, on_delete=models.CASCADE, verbose_name="مخزون القماش" , limit_choices_to={'product__product_type': 'fabric'})
    fabric_meters_allocated = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="أمتار القماش المخصصة")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="الحالة")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name="الأولوية")
    
    start_date = models.DateField(verbose_name="تاريخ البدء")
    expected_completion_date = models.DateField(verbose_name="تاريخ الإكمال المتوقع")
    actual_completion_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الإكمال الفعلي")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_production_orders', verbose_name="أنشأ بواسطة")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_production_orders', verbose_name="وافق عليه")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الموافقة")

    fabric_image = models.ImageField(upload_to='production/fabric_images/', blank=True, null=True, verbose_name="صورة القماش")
    minimum_stock_level = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الحد الأدنى للمخزون (متر)")
    start_time = models.TimeField(blank=True, null=True, verbose_name="وقت البدء")
    expected_completion_time = models.TimeField(blank=True, null=True, verbose_name="وقت الإنجاز المتوقع")
    bom_version = models.ForeignKey(BillOfMaterials, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="نسخة قائمة المواد")
    quality_level = models.CharField(max_length=20, choices=QUALITY_LEVELS, default='standard', verbose_name="مستوى الجودة")
    quality_requirements = models.TextField(blank=True, verbose_name="متطلبات الجودة")
    quality_check_required = models.BooleanField(default=True, verbose_name="فحص الجودة مطلوب")

    is_rush_order = models.BooleanField(default=False, verbose_name="أمر عاجل")

    customer_reference = models.CharField(max_length=100, blank=True, verbose_name="مرجع العميل")
    delivery_location = models.CharField(max_length=200, blank=True, verbose_name="موقع التسليم")

    special_instructions = models.TextField(blank=True, verbose_name="تعليمات خاصة")
    additional_notes = models.TextField(blank=True, verbose_name="ملاحظات إضافية")
    attachments = models.FileField(upload_to='production/attachments/', blank=True, null=True, verbose_name="مرفقات")

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    class Meta:
        verbose_name = "أمر إنتاج"
        verbose_name_plural = "أوامر الإنتاج"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"أمر إنتاج {self.order_number} - {self.product.name}"    
    def save(self, *args, **kwargs):
        # This logic runs only when a new order is being created
        if not self.pk:
            # --- CORRECTED: Sequential Order Number Generation ---
            if not self.order_number:
                today_str = timezone.now().strftime('%Y%m%d')
                last_order = ProductionOrder.objects.order_by('id').last()
                next_seq = 1
                if last_order and last_order.order_number and '-' in last_order.order_number:
                    try:
                        # Find the last sequential number from the string
                        last_seq_part = last_order.order_number.split('-')[-1]
                        next_seq = int(last_seq_part) + 1
                    except (ValueError, IndexError):
                        # Fallback if the format is unexpected
                        next_seq = (last_order.id or 0) + 1
                self.order_number = f"ORD-{today_str}-{next_seq}"

            # --- CORRECTED: Sequential Batch Number Generation ---
            if not self.batch_number:
                today_short_str = timezone.now().strftime('%y%m%d')
                product_code_prefix = self.product.code[:3].upper() if self.product.code else 'PROD'
                
                last_batch_order = ProductionOrder.objects.filter(
                    product__product_type=self.product.product_type,
                    batch_number__startswith=f'BATCH-{product_code_prefix}-'
                ).order_by('id').last()

                next_batch_seq = 1
                if last_batch_order and last_batch_order.batch_number:
                    try:
                        parts = last_batch_order.batch_number.split('-')
                        if len(parts) > 2:
                            last_seq = int(parts[2])
                            next_batch_seq = last_seq + 1
                    except (ValueError, IndexError):
                        next_batch_seq = ProductionOrder.objects.filter(product__product_type=self.product.product_type).count() + 1
                
                # Use the same next_id from the order number for the final part
                last_order_for_id = ProductionOrder.objects.order_by('id').last()
                order_id_part = (last_order_for_id.id + 1) if last_order_for_id else 1
                self.batch_number = f"BATCH-{product_code_prefix}-{next_batch_seq:04d}-{today_short_str}-{order_id_part}"

        super().save(*args, **kwargs)

    @property
    def total_fabric_required(self):
        """إجمالي القماش المطلوب"""
        return self.quantity_ordered * self.product.fabric_quantity_per_piece
    
    @property
    def progress_percentage(self):
        """نسبة التقدم"""
        status_progress = {
            'draft': 0,
            'approved': 10,
            'in_cutting': 25,
            'in_assembly': 50,
            'in_dyeing': 70,
            'in_finishing': 85,
            'completed': 100,
            'cancelled': 0,
        }
        return status_progress.get(self.status, 0)

class CuttingProcess(models.Model):
    """عملية القص"""
    production_order = models.OneToOneField(ProductionOrder, on_delete=models.CASCADE, related_name='cutting_process', verbose_name="أمر الإنتاج")
    cutting_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ القص")
    cutter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cutting_processes', verbose_name="القاص")
    single_layer_pieces = models.PositiveIntegerField(null=True, blank=True, verbose_name="عدد القطع في الطبقة الواحدة")
    single_layer_fabric_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="طول فرشة الطبقة الواحدة")
    single_layer_width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="عرض فرشة الطبقة الواحدة")
    single_layer_meterage = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="ميتراج القطعة للطبقة الواحدة")
    total_fabric_used = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إجمالي القماش المستخدم")
    total_pieces_cut = models.PositiveIntegerField(default=0, verbose_name="إجمالي القطع المقصوصة")
    fabric_waste = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="هدر القماش (متر)")
    marker_details = models.JSONField(null=True, blank=True, verbose_name="تفاصيل الرسمة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_completed = models.BooleanField(default=False, verbose_name="مكتمل")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإكمال")
    
    class Meta:
        verbose_name = "عملية قص"
        verbose_name_plural = "عمليات القص"
    
    def __str__(self):
        return f"قص {self.production_order.order_number}"
    
    def save(self, *args, **kwargs):
        """
        Overrides the save method to automatically calculate meterage and fabric waste.
        """
        # 1. Calculate the meterage per piece for the single layer
        if self.single_layer_fabric_length and self.single_layer_fabric_length > 0 and self.single_layer_pieces:
            self.single_layer_meterage = self.single_layer_fabric_length / Decimal(self.single_layer_pieces) 
        else:
            self.single_layer_meterage = None

        # 2. Calculate the fabric waste automatically
        # Ensure all required values are present and are numbers
        total_used = self.total_fabric_used or Decimal('0')
        total_pieces = self.total_pieces_cut or 0
        meterage = self.single_layer_meterage or Decimal('0')

        if total_used > 0 and total_pieces > 0 and meterage > 0:
            fabric_needed = meterage * Decimal(total_pieces)
            self.fabric_waste = total_used - fabric_needed
        else:
            # If any value is missing for the calculation, set waste to 0
            self.fabric_waste = Decimal('0')
            
        super().save(*args, **kwargs)
    def calculate_pieces_per_fabric(self, fabric_length, piece_length):
        """حساب عدد القطع من طول القماش"""
        if piece_length <= 0:
            return 0
        return int(fabric_length / piece_length)
    
    @property
    def actual_meterage(self):
        """Calculates the actual meterage based on total fabric used and total garments cut."""
        if self.total_fabric_used and self.total_pieces_cut:
            try:
                return self.total_fabric_used / self.total_pieces_cut
            except (TypeError, ZeroDivisionError):
                return Decimal('0.0')
        return Decimal('0.0')

class CuttingTable(models.Model):
    """جدول القص"""
    cutting_process = models.ForeignKey(CuttingProcess, on_delete=models.CASCADE, related_name='cutting_tables', verbose_name="عملية القص")
    fabric_length = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="طول الثوب (متر)")
    layers_count = models.PositiveIntegerField(verbose_name="عدد الطبقات")
    pieces_per_layer = models.PositiveIntegerField(verbose_name="القطع لكل طبقة")
    total_pieces = models.PositiveIntegerField(verbose_name="إجمالي القطع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "جدول قص"
        verbose_name_plural = "جداول القص"
    
    def __str__(self):
        return f"جدول قص - {self.fabric_length}م × {self.layers_count} طبقات"
    
    def save(self, *args, **kwargs):
        self.total_pieces = self.layers_count * self.pieces_per_layer
        super().save(*args, **kwargs)

class CutPiece(models.Model):
    """
    القطع المقصوصة
    This now represents the detailed inventory of individual cut components.
    """
    cutting_process = models.ForeignKey(CuttingProcess, on_delete=models.CASCADE, related_name='cut_pieces', verbose_name="عملية القص")
    
    # This is now a flexible CharField to store the component name from the BOM (e.g., "Front Right Panel")
    piece_type = models.CharField(max_length=100, verbose_name="نوع القطعة") 
    
    size = models.CharField(max_length=20, verbose_name="المقاس")
    quantity = models.PositiveIntegerField(verbose_name="الكمية")
    
    # Optional fields, can be removed if not necessary for your workflow
    length = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="الطول (سم)")
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="العرض (سم)")
    
    reserved_for_assembly = models.PositiveIntegerField(default=0, verbose_name="محجوز للتجميع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "قطعة مقصوصة"
        verbose_name_plural = "القطع المقصوصة"
        # Add index for faster lookups
        indexes = [
            models.Index(fields=['cutting_process', 'piece_type', 'size']),
        ]
        # Ensure we don't have duplicate entries for the same piece, size, and process
        unique_together = ('cutting_process', 'piece_type', 'size')

    def __str__(self):
        return f"{self.piece_type} - المقاس {self.size} (الكمية: {self.quantity})"
    
    @property
    def available_quantity(self):
        """
        Calculates the quantity available for the next production stage.
        Handles cases where quantity or reserved_for_assembly might be None.
        """
        # CORRECTION: Treat None as 0 to prevent TypeError
        quantity = self.quantity or 0
        reserved = self.reserved_for_assembly or 0
        return quantity - reserved
class ExternalManufacturer(models.Model):
    """المصنعين الخارجيين"""
    name = models.CharField(max_length=200, verbose_name="اسم المصنع")
    contact_person = models.CharField(max_length=100, verbose_name="الشخص المسؤول")
    phone = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    address = models.TextField(verbose_name="العنوان")
    payment_terms_days = models.PositiveIntegerField(default=30, verbose_name="مدة السداد بالأيام")
    quality_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name="تقييم الجودة"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "مصنع خارجي"
        verbose_name_plural = "المصانع الخارجية"
        ordering = ['name']
    def __str__(self):
        return self.name
    
    @property
    def total_orders(self):
        """إجمالي الأوامر"""
        return self.assembly_processes.count()
    
    @property
    def average_defect_rate(self):
        """متوسط معدل العيوب"""
        processes = self.assembly_processes.filter(is_completed=True)
        if not processes.exists():
            return 0
        total_sent = processes.aggregate(total=Sum('quantity_sent'))['total'] or 0
        total_defects = processes.aggregate(total=Sum('defects_count'))['total'] or 0
        if total_sent == 0:
            return 0
        return (total_defects / total_sent) * 100
    @property
    def active_jobs_count(self):
        """Counts all active assembly jobs for this manufacturer."""
        return self.assembly_processes.filter(is_completed=False).count()

    @property
    def total_completed_jobs(self):
        """Counts all completed assembly jobs for this manufacturer."""
        return self.assembly_processes.filter(is_completed=True).count()

    @property
    def total_value_of_active_jobs(self):
        """Calculates the potential total value of all active jobs."""
        # MODIFIED: This calculation now requires iterating through active jobs
        # and looking up the specific price for each product.
        active_processes = self.assembly_processes.filter(is_completed=False).select_related('production_order__product')
        total_value = Decimal('0.0')
        for process in active_processes:
            try:
                price_obj = ManufacturerProductPrice.objects.get(
                    manufacturer=self,
                    product=process.production_order.product
                )
                total_value += process.quantity_sent * price_obj.price
            except ManufacturerProductPrice.DoesNotExist:
                # If a price isn't set for an active job's product, it's not included in the total value.
                pass
        return total_value
    @property
    def financial_account(self):
        """
        Returns the associated finance Account for this manufacturer, if it exists.
        Returns None otherwise.
        This is used to easily access the account balance from manufacturer templates.
        """
        # Use a local import to prevent circular dependency errors
        from finance.models import Account 
        content_type = ContentType.objects.get_for_model(self)
        return Account.objects.filter(owner_content_type=content_type, owner_object_id=self.pk).first()

    @property
    def total_pieces_completed(self):
        """Calculates the total number of pieces successfully received from completed jobs."""
        total = self.assembly_processes.filter(is_completed=True).aggregate(
            total_pieces=Coalesce(Sum('quantity_received'), 0)
        )['total_pieces']
        return total

    
    

    @property
    def total_jobs_count(self):
        """Counts all jobs ever assigned to this manufacturer."""
        return self.assembly_processes.count()

class AssemblyProcess(models.Model):
    """
    عملية التجميع
    No changes are needed to this model itself, but its completion will now be the trigger
    to create a DyeingProcess instance, rather than directly changing the order status via a signal.
    """
    ASSEMBLY_TYPES = [
        ('in_house', 'داخلي'),
        ('outsourced', 'خارجي'),
    ]
    
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='assembly_processes', verbose_name="أمر الإنتاج")
    assembly_type = models.CharField(max_length=15, choices=ASSEMBLY_TYPES, verbose_name="نوع التجميع")
    external_manufacturer = models.ForeignKey(ExternalManufacturer, on_delete=models.SET_NULL, null=True, blank=True, related_name='assembly_processes', verbose_name="المصنع الخارجي")
    
    # للتجميع الداخلي
    assembler = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assembly_processes', verbose_name="المجمع")

    
    # الكميات
    quantity_sent = models.PositiveIntegerField(default=0, verbose_name="الكمية المرسلة")
    quantity_received = models.PositiveIntegerField(default=0, verbose_name="الكمية المستلمة")
    defects_count = models.PositiveIntegerField(default=0, verbose_name="عدد العيوب")
    losses_count = models.PositiveIntegerField(default=0, verbose_name="عدد الفاقد")
    
    # استهلاك الخيوط
    thread_consumption = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="استهلاك الخيوط (متر)")
    thread_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الخيوط")
    
    # التواريخ
    start_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ البدء")
    expected_completion_date = models.DateField(verbose_name="تاريخ الإكمال المتوقع")
    actual_completion_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإكمال الفعلي")
    
    # التكاليف
    assembly_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة التجميع")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    defect_notes = models.TextField(blank=True, verbose_name="ملاحظات العيوب")
    is_completed = models.BooleanField(default=False, verbose_name="مكتمل")
    
    
    @property
    def external_manufacturing_cost(self):
        """
        MODIFIED: Calculates the manufacturing cost by looking up the specific price
        for the product from the ManufacturerProductPrice table.
        """
        if self.assembly_type == 'outsourced' and self.external_manufacturer and self.production_order.product:
            try:
                # Look up the price in the new through-model
                price_obj = ManufacturerProductPrice.objects.get(
                    manufacturer=self.external_manufacturer,
                    product=self.production_order.product
                )
                # Use quantity_received for completed jobs, quantity_sent as fallback
                quantity = self.quantity_received if self.is_completed and self.quantity_received > 0 else self.quantity_sent
                return quantity * price_obj.price
            except ManufacturerProductPrice.DoesNotExist:
                # If no specific price is set, the cost is zero.
                return Decimal('0.00')
        return Decimal('0.00')

    def calculate_assembly_cost(self):
        """حساب تكلفة التجميع الكلية"""
        # This now correctly uses the property for the external cost
        total_cost = self.external_manufacturing_cost + self.thread_cost
        self.assembly_cost = total_cost
        # Use update_fields to prevent race conditions or overwriting other fields
        self.save(update_fields=['assembly_cost'])
    
    class Meta:
        verbose_name = "عملية تجميع"
        verbose_name_plural = "عمليات التجميع"
    
    def __str__(self):
        return f"تجميع {self.production_order.order_number} - {self.get_assembly_type_display()}"
    
    

    @property
    def defect_rate(self):
        """معدل العيوب"""
        if self.quantity_sent == 0:
            return 0
        return (self.defects_count / self.quantity_sent) * 100
    
    @property
    def loss_rate(self):
        """معدل الفاقد"""
        if self.quantity_sent == 0:
            return 0
        return (self.losses_count / self.quantity_sent) * 100
    


class AssemblyComponent(models.Model):
    """
    A component from the BOM sent along with an assembly process.
    """
    assembly_process = models.ForeignKey('AssemblyProcess', on_delete=models.CASCADE, related_name='components', verbose_name="عملية التجميع")
    material = models.ForeignKey('warehouses.Product', on_delete=models.PROTECT, verbose_name="المادة")
    quantity_sent = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الكمية المرسلة")
    source_warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="المخزن المصدر"
    )
    class Meta:
        verbose_name = "مكون تجميع مرسل"
        verbose_name_plural = "مكونات التجميع المرسلة"
        unique_together = ('assembly_process', 'material')

    def __str__(self):
        return f"{self.quantity_sent} x {self.material.name} for Assembly {self.assembly_process.id}"

        
        
class AssembledGarment(models.Model):
    """الملابس المجمعة"""
    assembly_process = models.ForeignKey(AssemblyProcess, on_delete=models.CASCADE, related_name='assembled_garments', verbose_name="عملية التجميع")
    size = models.CharField(max_length=10, verbose_name="المقاس")
    quantity = models.PositiveIntegerField(verbose_name="الكمية")
    quality_grade = models.CharField(max_length=10, choices=[('A', 'A'), ('B', 'B'), ('C', 'C')], default='A', verbose_name="درجة الجودة")
    product_code = models.CharField(max_length=200, verbose_name="كود المنتج")
    
    class Meta:
        verbose_name = "ملبس مجمع"
        verbose_name_plural = "الملابس المجمعة"
    
    def __str__(self):
        return f"{self.product_code} - {self.size} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        if not self.product_code:
            batch = self.assembly_process.production_order.batch_number
            product_name = self.assembly_process.production_order.product.name
            self.product_code = f"{product_name}+{batch}+Assembled Garment+{self.size}"
        super().save(*args, **kwargs)

class DyeingProcess(models.Model):
    """
    عملية الصباغة
    MODIFIED: Added fields for quality check images.
    """
    assembly_process = models.ForeignKey(AssemblyProcess, on_delete=models.CASCADE, related_name='dyeing_processes', verbose_name="عملية التجميع")
    dyeing_facility = models.ForeignKey(ExternalManufacturer, on_delete=models.PROTECT, related_name='dyeing_jobs', verbose_name="مصنع الصباغة")
    color_specification = models.CharField(max_length=100, verbose_name="مواصفات اللون")
    
    # الكميات
    quantity_sent = models.PositiveIntegerField(verbose_name="الكمية المرسلة")
    quantity_received = models.PositiveIntegerField(default=0, verbose_name="الكمية المستلمة")
    losses_count = models.PositiveIntegerField(default=0, verbose_name="عدد الفاقد")
    
    # التكاليف
    total_dyeing_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إجمالي تكلفة الصباغة")
    
    # التواريخ
    sent_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الإرسال")
    expected_return_date = models.DateField(verbose_name="تاريخ العودة المتوقع")
    actual_return_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ العودة الفعلي")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_completed = models.BooleanField(default=False, verbose_name="مكتمل")

    class Meta:
        verbose_name = "عملية صباغة"
        verbose_name_plural = "عمليات الصباغة"
    
    def __str__(self):
        return f"صباغة {self.assembly_process.production_order.order_number}"
    
    @property
    def loss_rate(self):
        """معدل الفاقد"""
        if self.quantity_sent == 0:
            return 0
        return (self.losses_count / self.quantity_sent) * 100
    
    def calculate_total_cost(self):
        """
        MODIFIED: Calculates total cost by looking up the product-specific price
        from the ManufacturerProductPrice table.
        """
        cost = Decimal('0.00')
        if self.dyeing_facility and self.assembly_process.production_order.product:
            try:
                price_obj = ManufacturerProductPrice.objects.get(
                    manufacturer=self.dyeing_facility,
                    product=self.assembly_process.production_order.product
                )
                quantity_to_cost = self.quantity_received if self.quantity_received > 0 else self.quantity_sent
                cost = quantity_to_cost * price_obj.price
            except ManufacturerProductPrice.DoesNotExist:
                # If no price is set for this product at this facility, cost remains zero
                pass
        
        self.total_dyeing_cost = cost
        # The view will handle saving the instance

        
class DyedGarment(models.Model):
    """الملابس المصبوغة"""
    dyeing_process = models.ForeignKey(DyeingProcess, on_delete=models.CASCADE, related_name='dyed_garments', verbose_name="عملية الصباغة")
    size = models.CharField(max_length=10, verbose_name="المقاس")
    quantity = models.PositiveIntegerField(verbose_name="الكمية")
    color_quality = models.CharField(max_length=10, choices=[('A', 'A'), ('B', 'B'), ('C', 'C')], default='A', verbose_name="جودة اللون")
    product_code = models.CharField(max_length=200, verbose_name="كود المنتج")
    
    class Meta:
        verbose_name = "ملبس مصبوغ"
        verbose_name_plural = "الملابس المصبوغة"
    
    def __str__(self):
        return f"{self.product_code} - {self.size} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        if not self.product_code:
            batch = self.dyeing_process.assembly_process.production_order.batch_number
            product_name = self.dyeing_process.assembly_process.production_order.product.name
            self.product_code = f"{product_name}+{batch}+Assembled & Dyed Garment+{self.size}"
        super().save(*args, **kwargs)


class FinishingProcess(models.Model):
    """
    عملية التشطيب
    MODIFIED: This model now supports both in-house and outsourced finishing,
    similar to the AssemblyProcess model.
    """
    FINISHING_TYPES = [
        ('in_house', 'داخلي'),
        ('outsourced', 'خارجي'),
    ]
    
    dyeing_process = models.OneToOneField(DyeingProcess, on_delete=models.CASCADE, related_name='finishing_process', verbose_name="عملية الصباغة")
    
    # NEW: Fields to support in-house vs. outsourced
    finishing_type = models.CharField(max_length=15, choices=FINISHING_TYPES, default='in_house', verbose_name="نوع التشطيب")
    external_manufacturer = models.ForeignKey(ExternalManufacturer, on_delete=models.SET_NULL, null=True, blank=True, related_name='finishing_jobs', verbose_name="المصنع الخارجي")
    finisher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='finishing_processes', verbose_name="مسؤول التشطيب الداخلي")

    destination_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المخزن النهائي")
    
    # Checklist fields for the timeline UI
    ironing_completed = models.BooleanField(default=False, verbose_name="الكي مكتمل")
    belt_loops_completed = models.BooleanField(default=False, verbose_name="عراوي الحزام مكتملة")
    buttons_completed = models.BooleanField(default=False, verbose_name="الأزرار مكتملة")
    leather_details_completed = models.BooleanField(default=False, verbose_name="التفاصيل الجلدية مكتملة")
    cleaning_completed = models.BooleanField(default=False, verbose_name="التنظيف مكتمل")
    pressing_completed = models.BooleanField(default=False, verbose_name="الكبس مكتمل")
    ticketing_completed = models.BooleanField(default=False, verbose_name="وضع التذاكر مكتمل")
    bagging_completed = models.BooleanField(default=False, verbose_name="التعبئة مكتملة")
    packaging_completed = models.BooleanField(default=False, verbose_name="التغليف مكتمل")
    
    # الكميات
    quantity_input = models.PositiveIntegerField(verbose_name="الكمية المدخلة")
    quantity_output = models.PositiveIntegerField(default=0, verbose_name="الكمية المخرجة")
    defects_in_finishing = models.PositiveIntegerField(default=0, verbose_name="العيوب في التشطيب")
    receipt_history = models.JSONField(default=list, blank=True, verbose_name="سجل دفعات الاستلام")

    # التكاليف
    # REMOVED: finishing_cost_per_piece
    total_finishing_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إجمالي تكلفة التشطيب")
    
    # المسؤولين
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_finishing_processes', verbose_name="المشرف")
    
    # التواريخ
    start_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ البدء")
    expected_completion_date = models.DateField(verbose_name="تاريخ الإكمال المتوقع")
    actual_completion_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإكمال الفعلي")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_completed = models.BooleanField(default=False, verbose_name="مكتمل")
    
    class Meta:
        verbose_name = "عملية تشطيب"
        verbose_name_plural = "عمليات التشطيب"
    
    def __str__(self):
        return f"تشطيب {self.dyeing_process.assembly_process.production_order.order_number}"
    
    def get_absolute_url(self):
        return reverse('production:finishing_detail', kwargs={'pk': self.pk})

    def calculate_total_cost(self):
        """
        Calculates the total finishing cost based on finishing type and BOM components.
        This function is called before saving the model.
        """
        total_cost = Decimal('0.00')
        
        # 1. Cost from BOM components (accessories, etc.)
        # Get the BOM associated with the production order
        production_order = self.dyeing_process.assembly_process.production_order
        bom = production_order.bom_version

        if bom:
            # Sum the cost of all BOM items (excluding fabric which is handled in cutting)
            # This assumes BOM items have a 'cost' property or can calculate it.
            # We'll filter for non-fabric items as finishing uses accessories.
            bom_components_cost = bom.items.exclude(material__product_type='fabric').aggregate(
                total=Sum(F('quantity') * F('material__cost_price'))
            )['total'] or Decimal('0.00')
            
            # Multiply by the quantity being finished
            total_cost += bom_components_cost * self.quantity_input

        # 2. External Manufacturer Cost (if outsourced)
        if self.finishing_type == 'outsourced' and self.external_manufacturer:
            try:
                # Look up the product-specific price
                price_obj = ManufacturerProductPrice.objects.get(
                    manufacturer=self.external_manufacturer,
                    product=production_order.product
                )
                total_cost += self.quantity_input * price_obj.price
            except ManufacturerProductPrice.DoesNotExist:
                # If no price is set, no cost is added for external manufacturing
                pass

        self.total_finishing_cost = total_cost
 
        # Note: We don't save here directly, as this is called within a form_valid which will save. 
class FinishingComponent(models.Model):
    """
    A component from the BOM sent along with a finishing process.
    """
    finishing_process = models.ForeignKey('FinishingProcess', on_delete=models.CASCADE, related_name='components', verbose_name="عملية التشطيب")
    material = models.ForeignKey('warehouses.Product', on_delete=models.PROTECT, verbose_name="المادة")
    quantity_sent = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الكمية المرسلة")
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المخزن المصدر"
    )
    class Meta:
        verbose_name = "مكون تشطيب مرسل"
        verbose_name_plural = "مكونات التشطيب المرسلة"
        unique_together = ('finishing_process', 'material')

    def __str__(self):
        return f"{self.quantity_sent} x {self.material.name} for Finishing {self.finishing_process.id}"
    

class ProcessDocument(models.Model):
    """مستندات العمليات"""
    DOCUMENT_TYPES = [
        ('cutting_order', 'أمر قص'),
        ('assembly_order', 'أمر تجميع'),
        ('dyeing_order', 'أمر صباغة'),
        ('finishing_order', 'أمر تشطيب'),
        ('quality_report', 'تقرير جودة'),
        ('cost_analysis', 'تحليل تكلفة'),
    ]
    
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='documents', verbose_name="أمر الإنتاج")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, verbose_name="نوع المستند")
    document_number = models.CharField(max_length=50, verbose_name="رقم المستند")
    title = models.CharField(max_length=200, verbose_name="عنوان المستند")
    content = models.TextField(verbose_name="محتوى المستند")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="أنشأ بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "مستند عملية"
        verbose_name_plural = "مستندات العمليات"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_document_type_display()} - {self.document_number}"

class ExitPermit(models.Model):
    """تصاريح الخروج"""
    PERMIT_TYPES = [
        ('cutting_materials', 'مواد القص'),
        ('assembly_pieces', 'قطع التجميع'),
        ('dyeing_garments', 'ملابس للصباغة'), # Note: Corrected typo 'garments'
        ('finishing_products', 'منتجات التشطيب'),
        ('other', 'أخرى'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'معلق'),
        ('approved', 'موافق عليه'),
        ('rejected', 'مرفوض'),
        ('used', 'مستخدم'),
        ('expired', 'منتهي الصلاحية'),
    ]
    assembly_process = models.ForeignKey(
        'AssemblyProcess',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exit_permits',
        verbose_name="عملية التجميع المرتبطة"
    )
    dyeing_process = models.ForeignKey(
        'DyeingProcess',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exit_permits',
        verbose_name="عملية الصباغة المرتبطة"
    )
    finishing_process = models.ForeignKey(
        'FinishingProcess',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exit_permits',
        verbose_name="عملية التشطيب المرتبطة"
    )
    permit_number = models.CharField(max_length=50, unique=True,blank=True, verbose_name="رقم التصريح")
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='exit_permits', verbose_name="أمر الإنتاج")
    permit_type = models.CharField(max_length=20, choices=PERMIT_TYPES, verbose_name="نوع التصريح")
    
    # تفاصيل التصريح
    items_description = models.TextField(verbose_name="وصف المواد")
    quantity = models.PositiveIntegerField(verbose_name="الكمية")
    destination = models.CharField(max_length=200, verbose_name="الوجهة")
    purpose = models.TextField(verbose_name="الغرض")
    
    # الموافقات
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name="الحالة")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_exit_permits', verbose_name="طلب بواسطة")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_exit_permits', verbose_name="وافق عليه")
    
    # التواريخ
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الموافقة")
    valid_until = models.DateTimeField(verbose_name="صالح حتى")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاستخدام")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "تصريح خروج"
        verbose_name_plural = "تصاريح الخروج"
        ordering = ['-requested_at']

    def save(self, *args, **kwargs):
        # Auto-populate production order from the related process if not set
        if not self.production_order_id:
            if self.assembly_process_id:
                self.production_order = self.assembly_process.production_order
            elif self.dyeing_process_id:
                self.production_order = self.dyeing_process.assembly_process.production_order
            elif self.finishing_process_id:
                self.production_order = self.finishing_process.dyeing_process.assembly_process.production_order
        
        if not self.permit_number:
            today_str = timezone.now().strftime('%Y%m%d')
            today_permits = ExitPermit.objects.filter(permit_number__startswith=f"EP-{today_str}").count()
            self.permit_number = f"EP-{today_str}-{today_permits + 1:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.permit_number

    def get_absolute_url(self):
        """Returns the URL to the detail page for this specific permit."""
        return reverse('production:exit_permits:exit_permit_detail', kwargs={'pk': self.pk})
    @property
    def is_expired(self):
        return timezone.now() > self.valid_until and self.status not in ['used', 'rejected']

    @property
    def is_approvable(self):
        return self.status == 'pending'

    @property
    def is_usable(self):
        return self.status == 'approved' and not self.is_expired
    

class ReceiptConfirmation(models.Model):
    """تأكيدات الاستلام"""
    exit_permit = models.OneToOneField(ExitPermit, on_delete=models.CASCADE, related_name='receipt_confirmation', verbose_name="تصريح الخروج")
    
    # معلومات المستلم
    received_by_name = models.CharField(max_length=100, verbose_name="اسم المستلم")
    received_by_signature = models.TextField(verbose_name="توقيع المستلم")
    company_representative = models.CharField(max_length=100, blank=True, verbose_name="ممثل الشركة")
    
    # تفاصيل الاستلام
    quantity_received = models.PositiveIntegerField(verbose_name="الكمية المستلمة")
    condition_notes = models.TextField(blank=True, verbose_name="ملاحظات الحالة")
    quality_check_passed = models.BooleanField(default=True, verbose_name="اجتاز فحص الجودة")
    
    # التواريخ
    received_at = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الاستلام")
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='receipt_confirmations', verbose_name="أكد بواسطة")
    
    # مرفقات
    photo_evidence = models.ImageField(upload_to='receipt_photos/', blank=True, null=True, verbose_name="صورة إثبات")
    additional_documents = models.FileField(upload_to='receipt_documents/', blank=True, null=True, verbose_name="مستندات إضافية")
    
    class Meta:
        verbose_name = "تأكيد استلام"
        verbose_name_plural = "تأكيدات الاستلام"
    
    def __str__(self):
        return f"استلام {self.exit_permit.permit_number} - {self.received_by_name}"
    
    @property
    def quantity_variance(self):
        """فرق الكمية"""
        return self.quantity_received - self.exit_permit.quantity

class ProductionCostAnalysis(models.Model):
    """تحليل تكلفة الإنتاج"""
    production_order = models.OneToOneField(ProductionOrder, on_delete=models.CASCADE, related_name='cost_analysis', verbose_name="أمر الإنتاج")
    
    # تكاليف المواد الخام
    fabric_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="تكلفة القماش")
    thread_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الخيوط")
    accessories_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الإكسسوارات")
    
    # تكاليف العمليات
    cutting_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة القص")
    assembly_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة التجميع")
    dyeing_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الصباغة")
    finishing_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة التشطيب")
    
    # تكاليف إضافية
    transportation_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="تكلفة النقل")
    overhead_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="التكاليف العامة")
    quality_control_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="تكلفة مراقبة الجودة")
    
    # الفاقد والعيوب
    waste_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الفاقد")
    defect_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة العيوب")
    
    # الإجماليات
    total_material_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="إجمالي تكلفة المواد")
    total_process_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="إجمالي تكلفة العمليات")
    total_additional_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="إجمالي التكاليف الإضافية")
    total_production_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="إجمالي تكلفة الإنتاج")
    
    # تكلفة القطعة
    cost_per_piece = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة القطعة")
    
    # معلومات التحليل
    analyzed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cost_analyses', verbose_name="حلل بواسطة")
    analysis_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التحليل")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "تحليل تكلفة إنتاج"
        verbose_name_plural = "تحليلات تكلفة الإنتاج"
    
    def __str__(self):
        return f"تحليل تكلفة {self.production_order.order_number}"
    
    def calculate_totals(self):
        """حساب الإجماليات"""
        # إجمالي تكلفة المواد
        self.total_material_cost = (
            self.fabric_cost + 
            self.thread_cost + 
            self.accessories_cost
        )
        
        # إجمالي تكلفة العمليات
        self.total_process_cost = (
            self.cutting_cost + 
            self.assembly_cost + 
            self.dyeing_cost + 
            self.finishing_cost
        )
        
        # إجمالي التكاليف الإضافية
        self.total_additional_cost = (
            self.transportation_cost + 
            self.overhead_cost + 
            self.quality_control_cost + 
            self.waste_cost + 
            self.defect_cost
        )
        
        # إجمالي تكلفة الإنتاج
        self.total_production_cost = (
            self.total_material_cost + 
            self.total_process_cost + 
            self.total_additional_cost
        )
        
        # تكلفة القطعة
        if self.production_order.quantity_ordered > 0:
            self.cost_per_piece = self.total_production_cost / self.production_order.quantity_ordered
        
        self.save()
    
    @property
    def material_cost_percentage(self):
        """نسبة تكلفة المواد"""
        if self.total_production_cost == 0:
            return 0
        return (self.total_material_cost / self.total_production_cost) * 100
    
    @property
    def process_cost_percentage(self):
        """نسبة تكلفة العمليات"""
        if self.total_production_cost == 0:
            return 0
        return (self.total_process_cost / self.total_production_cost) * 100
    
    @property
    def waste_percentage(self):
        """نسبة الفاقد"""
        if self.total_production_cost == 0:
            return 0
        return ((self.waste_cost + self.defect_cost) / self.total_production_cost) * 100

class QualityControlCheck(models.Model):
    """فحص مراقبة الجودة"""
    CHECK_TYPES = [
        ('fabric_inspection', 'فحص القماش'),
        ('cutting_quality', 'جودة القص'),
        ('assembly_quality', 'جودة التجميع'),
        ('dyeing_quality', 'جودة الصباغة'),
        ('finishing_quality', 'جودة التشطيب'),
        ('final_inspection', 'الفحص النهائي'),
    ]
    
    QUALITY_GRADES = [
        ('A', 'ممتاز'),
        ('B', 'جيد'),
        ('C', 'مقبول'),
        ('D', 'غير مقبول'),
    ]
    
    production_order = models.ForeignKey('ProductionOrder', on_delete=models.CASCADE, related_name='quality_checks', verbose_name="أمر الإنتاج")
    
    # Links to specific processes
    cutting_process = models.ForeignKey(
        'CuttingProcess', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='quality_checks',
        verbose_name="عملية القص"
    )
    assembly_process = models.ForeignKey(
        'AssemblyProcess', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='quality_checks',
        verbose_name="عملية التجميع"
    )
    dyeing_process = models.ForeignKey(
        'DyeingProcess', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='quality_checks',
        verbose_name="عملية الصباغة"
    )
    finishing_process = models.ForeignKey(
        'FinishingProcess', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='quality_checks',
        verbose_name="عملية التشطيب"
    )

    check_type = models.CharField(max_length=20, choices=CHECK_TYPES, verbose_name="نوع الفحص")
    check_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الفحص")
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='quality_inspections', verbose_name="المفتش")
    
    # نتائج الفحص
    items_checked = models.PositiveIntegerField(verbose_name="العناصر المفحوصة")
    items_passed = models.PositiveIntegerField(verbose_name="العناصر المقبولة")
    items_failed = models.PositiveIntegerField(default=0, verbose_name="العناصر المرفوضة")
    
    overall_grade = models.CharField(max_length=1, choices=QUALITY_GRADES, verbose_name="التقييم العام")
    
    # تفاصيل العيوب
    defect_description = models.TextField(blank=True, verbose_name="وصف العيوب")
    corrective_actions = models.TextField(blank=True, verbose_name="الإجراءات التصحيحية")
    
    # الموافقة
    approved = models.BooleanField(default=False, verbose_name="موافق عليه")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_quality_checks', verbose_name="وافق عليه")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "فحص جودة"
        verbose_name_plural = "فحوصات الجودة"
        ordering = ['-check_date']
    
    def __str__(self):
        return f"فحص {self.get_check_type_display()} - {self.production_order.order_number}"

    def get_absolute_url(self):
        return reverse('production:quality:quality_detail', kwargs={'pk': self.pk})
    
    @property
    def pass_rate(self):
        """معدل النجاح"""
        if self.items_checked == 0:
            return 0
        return (self.items_passed / self.items_checked) * 100
    
    @property
    def failure_rate(self):
        """معدل الفشل"""
        if self.items_checked == 0:
            return 0
        return (self.items_failed / self.items_checked) * 100

    @property
    def related_process(self):
        """Returns the specific process this check is linked to."""
        if self.cutting_process:
            return self.cutting_process
        if self.assembly_process:
            return self.assembly_process
        if self.dyeing_process:
            return self.dyeing_process
        if self.finishing_process:
            return self.finishing_process
        return None

    @property
    def related_process_url(self):
        """Returns the URL of the specific process this check is linked to."""
        process = self.related_process
        if process and hasattr(process, 'get_absolute_url'):
            return process.get_absolute_url()
        return None

class ProductionReport(models.Model):
    """تقارير الإنتاج"""
    REPORT_TYPES = [
        ('daily', 'يومي'),
        ('weekly', 'أسبوعي'),
        ('monthly', 'شهري'),
        ('order_summary', 'ملخص أمر'),
        ('cost_analysis', 'تحليل تكلفة'),
        ('quality_report', 'تقرير جودة'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, verbose_name="نوع التقرير")
    title = models.CharField(max_length=200, verbose_name="عنوان التقرير")
    
    # الفترة الزمنية
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    
    # البيانات
    total_orders = models.PositiveIntegerField(default=0, verbose_name="إجمالي الأوامر")
    completed_orders = models.PositiveIntegerField(default=0, verbose_name="الأوامر المكتملة")
    total_pieces_produced = models.PositiveIntegerField(default=0, verbose_name="إجمالي القطع المنتجة")
    total_production_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="إجمالي تكلفة الإنتاج")
    
    # معدلات الجودة
    average_quality_score = models.DecimalField(max_digits=4, decimal_places=2, default=0, verbose_name="متوسط نقاط الجودة")
    defect_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="معدل العيوب")
    waste_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="معدل الفاقد")
    
    # تفاصيل التقرير
    report_content = models.TextField(verbose_name="محتوى التقرير")
    recommendations = models.TextField(blank=True, verbose_name="التوصيات")
    
    # معلومات التقرير
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='production_reports', verbose_name="أنشأ بواسطة")
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "تقرير إنتاج"
        verbose_name_plural = "تقارير الإنتاج"
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.title}"
    
    @property
    def completion_rate(self):
        """معدل الإكمال"""
        if self.total_orders == 0:
            return 0
        return (self.completed_orders / self.total_orders) * 100
    
    @property
    def average_cost_per_piece(self):
        """متوسط تكلفة القطعة"""
        if self.total_pieces_produced == 0:
            return 0
        return self.total_production_cost / self.total_pieces_produced

# إشارات Django لتحديث الحالات تلقائياً
from django.db.models.signals import post_save




class GarmentDraw(models.Model):
    bom = models.ForeignKey(
        BillOfMaterials, 
        on_delete=models.CASCADE, 
        related_name='draws', 
        verbose_name="قائمة المواد (BOM)"
    )
    size = models.CharField(max_length=50, verbose_name="المقاس")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="تم الإنشاء بواسطة")

    class Meta:
        verbose_name = "رسمة قص"
        verbose_name_plural = "رسومات القص"
        # ضمان عدم تكرار نفس الرسمة لنفس المقاس ونفس الـ BOM
        unique_together = ('bom', 'size')
        ordering = ['bom', 'size']

    def __str__(self):
        return f"رسمة قص لـ {self.bom.product.name} - مقاس {self.size}"

    def get_absolute_url(self):
        # --- CORRECTION ---
        # The correct URL name includes the 'draws' namespace.
        return reverse('production:draws:draw_detail', kwargs={'pk': self.pk})

# =============================================================================
#  NEW MODEL: DrawPiece
#  هذه هي القطعة الفردية داخل "رسمة القص".
# =============================================================================
class DrawPiece(models.Model):
    draw = models.ForeignKey(
        GarmentDraw, 
        on_delete=models.CASCADE, 
        related_name='pieces', 
        verbose_name="رسمة القص"
    )
    name = models.CharField(max_length=150, verbose_name="اسم القطعة")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    
    class Meta:
        verbose_name = "قطعة في الرسمة"
        verbose_name_plural = "قطع الرسمة"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (x{self.quantity})"

