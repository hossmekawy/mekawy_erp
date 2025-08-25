# Django imports
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal

# Project imports
from crm.models import Customer
from warehouses.models import Product, Warehouse, StockItem

class PriceList(models.Model):
    """
    قوائم الأسعار: جملة/جملة-جملة/عملاء محددين/مواسم.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم قائمة الأسعار")
    is_active = models.BooleanField(default=True, verbose_name="نشطة")
    start_date = models.DateField(null=True, blank=True, verbose_name="تاريخ البدء")
    end_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الانتهاء")

    class Meta:
        verbose_name = "قائمة أسعار"
        verbose_name_plural = "قوائم الأسعار"

    def __str__(self):
        return self.name

class PriceListItem(models.Model):
    """
    سعر منتج معين في قائمة أسعار.
    """
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='items', verbose_name="قائمة الأسعار")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_list_items', verbose_name="المنتج")
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="السعر")

    class Meta:
        verbose_name = "بند قائمة أسعار"
        verbose_name_plural = "بنود قوائم الأسعار"
        unique_together = ('price_list', 'product')

    def __str__(self):
        return f"{self.product.name} in {self.price_list.name}: {self.price}"


class SalesInvoice(models.Model):
    """
    فاتورة المبيعات
    """
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('submitted', 'مقدمة'),
        ('paid', 'مدفوعة'),
        ('cancelled', 'ملغية'),
    ]
    PAYMENT_TERMS_CHOICES = [
        ('cash', 'نقدي'),
        ('due_on_receipt', 'الدفع عند الاستلام'),
        ('net_15', 'صافي 15 يوم'),
        ('net_30', 'صافي 30 يوم'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices', verbose_name="العميل")
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الفاتورة", editable=False, blank=True)
    issue_date = models.DateField(default=timezone.now, verbose_name="تاريخ الإصدار")
    due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="الحالة")
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='cash', verbose_name="شروط الدفع")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, verbose_name="المستودع")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="المجموع الفرعي")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الخصم")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الضريبة")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الإجمالي")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "فاتورة مبيعات"
        verbose_name_plural = "فواتير المبيعات"
        ordering = ['-issue_date']

    def __str__(self):
        return self.invoice_number

    def get_absolute_url(self):
        return reverse('sales:invoice_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last_invoice = SalesInvoice.objects.all().order_by('id').last()
            if not last_invoice:
                new_inv_id = 1
            else:
                new_inv_id = (last_invoice.id or 0) + 1
            self.invoice_number = f'INV-{new_inv_id:04d}'
        super().save(*args, **kwargs)


    def calculate_totals(self):
        items = self.items.all()
        self.subtotal = sum(item.total for item in items)
        self.total = self.subtotal - self.discount_amount + self.tax_amount
        self.save()


class InvoiceItem(models.Model):
    """
    بند في فاتورة المبيعات
    """
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='items', verbose_name="الفاتورة")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="المنتج")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر الوحدة")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة الخصم")
    total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الإجمالي")

    class Meta:
        verbose_name = "بند فاتورة"
        verbose_name_plural = "بنود الفاتورة"

    def save(self, *args, **kwargs):
        self.total = (self.quantity * self.unit_price) * (1 - self.discount_percentage / 100)
        super().save(*args, **kwargs)
        self.invoice.calculate_totals()

    def __str__(self):
        return f"{self.quantity} x {self.product.name} @ {self.unit_price}"
