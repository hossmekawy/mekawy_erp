from django.db import models
from django.contrib.auth import get_user_model  
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from django.conf import settings

User = get_user_model() 
# التصنيفات
class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم التصنيف")
    description = models.TextField(blank=True, verbose_name="الوصف")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    class Meta:
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"
    
    def __str__(self):
        return self.name

class Unit(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="اسم الوحدة")
    symbol = models.CharField(max_length=10, verbose_name="الرمز")
    is_base_unit = models.BooleanField(default=False, verbose_name="وحدة أساسية")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "وحدة"
        verbose_name_plural = "الوحدات"
    
    def __str__(self):
        return f"{self.name} ({self.symbol})"

class UnitConversion(models.Model):
    from_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_from', verbose_name="من الوحدة")
    to_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_to', verbose_name="إلى الوحدة")
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="معامل التحويل")
    # Example: 1 شيكارة = 48 قطعة, so conversion_factor = 48
    
    class Meta:
        unique_together = ['from_unit', 'to_unit']
        verbose_name = "تحويل وحدة"
        verbose_name_plural = "تحويلات الوحدات"
    
    def __str__(self):
        return f"1 {self.from_unit.name} = {self.conversion_factor} {self.to_unit.name}"
    
    @classmethod
    def convert_quantity(cls, quantity, from_unit, to_unit):
        """Convert quantity from one unit to another"""
        if from_unit == to_unit:
            return quantity
        quantity = Decimal(str(quantity))
        try:
            # Direct conversion
            conversion = cls.objects.get(from_unit=from_unit, to_unit=to_unit)
            result = quantity * conversion.conversion_factor
            return float(result)
        except cls.DoesNotExist:
            try:
                # Reverse conversion
                conversion = cls.objects.get(from_unit=to_unit, to_unit=from_unit)
                result = quantity / conversion.conversion_factor
                return float(result)
            except cls.DoesNotExist:
                # No direct conversion found
                raise ValueError(f"لا يمكن التحويل من {from_unit.name} إلى {to_unit.name}")

# المخازن
class Warehouse(models.Model):
    """
    Represents a physical or logical warehouse for storing products.
    The `warehouse_type` allows for segregation of raw materials and finished goods.
    """
    WAREHOUSE_TYPE_CHOICES = (
        ('textile', _('Textile Warehouse / مخزن أقمشة')),
        ('finished_goods', _('Finished Goods Warehouse / مخزن منتجات نهائية')),
        ('components', _('Components Warehouse / مخزن مكونات')),
        ('other', _('Other / أخرى')),
    )
    name = models.CharField(max_length=255, verbose_name=_('Warehouse Name / اسم المخزن'))
    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name=_('Warehouse Code / كود المخزن'))

    location = models.CharField(max_length=255, blank=True, verbose_name=_('Location / الموقع'))
    warehouse_type = models.CharField(
        max_length=20,
        choices=WAREHOUSE_TYPE_CHOICES,
        default='other',
        verbose_name=_('Warehouse Type / نوع المخزن')
    )
    description = models.TextField(blank=True, verbose_name=_("Description / الوصف"))
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Manager / المدير")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active / نشط"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At / تاريخ الإنشاء"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last Updated / آخر تعديل"))


    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Warehouse')
        verbose_name_plural = _('Warehouses')
# المنتجات (للملابس)
class Product(models.Model):
    UNIT_CHOICES = [
        ('piece', 'قطعة'),
        ('dozen', 'دستة (12 قطعة)'),
        ('sarya6', 'ساريه (6 قطع)'),
        ('sarya4', 'ساريه (4 قطع)'),
        ('shk48', 'شيكارة (48 قطعة)'),
        ('shk30', 'شيكارة (30 قطعة)'),
        ('kg', 'كيلوجرام'),
        ('meter', 'متر'),
        ('roll', 'لفة'),
    ]
    
    PRODUCT_TYPES = [
        ('fabric', 'قماش'),
        ('thread', 'خيط'),
        ('button', 'أزرار'),
        ('zipper', 'سحاب'),
        ('accessory', 'إكسسوار'),
        ('finished', 'منتج نهائي'),
    ]

    name = models.CharField(max_length=200, verbose_name="اسم المنتج")
    code = models.CharField(max_length=50, unique=True, verbose_name="كود المنتج")
    barcode = models.CharField(max_length=100, blank=True, verbose_name="الباركود")
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, verbose_name="الفئة")
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES, default='fabric', verbose_name="نوع المنتج")
    
    # Common Fields
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="سعر التكلفة")
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='piece', verbose_name="الوحدة")
    unit_new = models.ForeignKey('Unit', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة الجديدة")
    min_stock_level = models.PositiveIntegerField(default=0, verbose_name="الحد الأدنى للمخزون")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    # == Fields for Textile (قماش) ==
    colors = models.CharField(max_length=255, blank=True, null=True, verbose_name="الألوان المتاحة")
    width = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="العرض (سم)")
    quality_grade = models.CharField(max_length=10, choices=[('A', 'A'), ('B', 'B'), ('C', 'C')], null=True, blank=True, default='A', verbose_name="درجة الجودة")

    # == Fields for Finished Product (منتج نهائي) ==
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="سعر البيع")
    size_group = models.ForeignKey('production.SizeGroup', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="مجموعة المقاسات")
    fabric_quantity_per_piece = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="كمية القماش للقطعة")

    class Meta:
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def total_stock(self):
        return sum(item.quantity for item in self.stock_items.all())



# عنصر مخزون
class StockItem(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_items', verbose_name="المخزن")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_items', verbose_name="المنتج")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="الكمية")
    reserved_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="الكمية المحجوزة")
    location = models.CharField(max_length=100, blank=True, verbose_name="الموقع")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    class Meta:
        unique_together = ['warehouse', 'product']
        verbose_name = "عنصر مخزون"
        verbose_name_plural = "عناصر المخزون"
    
    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name} ({self.quantity})"
    
    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.product.min_stock_level
    
    @property
    def total_value(self):
        """Calculate total value of this stock item"""
        return float(self.quantity) * float(self.product.cost_price)

# حركات المخزون
class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'وارد'),
        ('out', 'صادر'),
        ('transfer', 'تحويل'),
        ('adjustment', 'تسوية'),
        ('return', 'مرتجع'),
    ]
    
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='movements', verbose_name="عنصر المخزون")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, verbose_name="نوع الحركة")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الكمية")
    reference_number = models.CharField(max_length=100, blank=True, verbose_name="رقم المرجع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="أنشأ بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الحركة")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "حركة مخزون"
        verbose_name_plural = "حركات المخزون"
    
    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.stock_item.product.name} ({self.quantity})"

# تحويل المخزون بين المخازن
class StockTransfer(models.Model):
    TRANSFER_STATUS = [
        ('pending', 'في الانتظار'),
        ('approved', 'موافق عليه'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ]
    
    transfer_number = models.CharField(max_length=50, unique=True, verbose_name="رقم التحويل")
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transfers_out', verbose_name="من المخزن")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transfers_in', verbose_name="إلى المخزن")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="المنتج")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الكمية")
    reason = models.TextField(verbose_name="سبب التحويل")
    status = models.CharField(max_length=20, choices=TRANSFER_STATUS, default='pending', verbose_name="الحالة")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_transfers', verbose_name="طلب بواسطة")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_transfers', verbose_name="وافق بواسطة")
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_transfers', verbose_name="أكمل بواسطة")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الموافقة")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإكمال")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    class Meta:
        ordering = ['-requested_at']
        verbose_name = "تحويل مخزون"
        verbose_name_plural = "تحويلات المخزون"
    
    def __str__(self):
        return f"تحويل {self.transfer_number}: {self.product.name} من {self.from_warehouse.name} إلى {self.to_warehouse.name}"


# Add this new model to your warehouses/models.py file

class ProductBatch(models.Model):
    """
    Tracks the inventory of a specific production batch of a finished product
    in a particular warehouse.
    """
    # --- FIX: This now links to the StockItem, which contains both product and warehouse info. ---
    stock = models.ForeignKey(
        StockItem, 
        on_delete=models.CASCADE, 
        related_name='batches', 
        verbose_name="عنصر المخزون"
    )
    batch_number = models.CharField(max_length=100, db_index=True, verbose_name="رقم الدفعة")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الكمية")
    cost_per_piece = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة القطعة")
    
    # --- FIX: The field now correctly points to 'production.FinishingProcess' ---
    # This is the true source of a finished product batch.
    production_finishing_source = models.OneToOneField(
        'production.FinishingProcess', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='warehouse_batch'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "دفعة منتج"
        verbose_name_plural = "دفعات المنتجات"
        # --- FIX: The unique_together constraint now uses the 'stock' field. ---
        unique_together = ('stock', 'batch_number')
        ordering = ['-created_at']

    def __str__(self):
        # Use properties to avoid database errors if stock is not loaded
        product_name = self.stock.product.name if self.stock and self.stock.product else 'N/A'
        warehouse_name = self.stock.warehouse.name if self.stock and self.stock.warehouse else 'N/A'
        return f"Batch {self.batch_number} of {product_name} ({self.quantity}) in {warehouse_name}"

    # --- FIX: Added properties to easily access product and warehouse from the batch ---
    @property
    def product(self):
        if self.stock:
            return self.stock.product
        return None

    @property
    def warehouse(self):
        if self.stock:
            return self.stock.warehouse
        return None
