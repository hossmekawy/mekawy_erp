# Django imports
import uuid
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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="المنتج")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر")

    class Meta:
        verbose_name = "بند قائمة أسعار"
        verbose_name_plural = "بنود قوائم الأسعار"
        unique_together = ('price_list', 'product')

    def __str__(self):
        return f"{self.product.name} in {self.price_list.name}"

class SalesInvoice(models.Model):
    """
    فاتورة المبيعات
    """
    STATUS_CHOICES = [
        ('DRAFT', 'مسودة'),
        ('PENDING', 'معلقة'),
        ('PAID', 'مدفوعة'),
        ('CANCELLED', 'ملغاة'),
    ]
    
    # New field for official e-invoicing
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")
    
    invoice_number = models.CharField(max_length=20, unique=True, editable=False, verbose_name="رقم الفاتورة")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="العميل")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="المخزن")
    issue_date = models.DateField(default=timezone.now, verbose_name="تاريخ الإصدار")
    due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING', verbose_name="الحالة")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الإجمالي الفرعي")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الخصم")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مبلغ الضريبة")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الإجمالي")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sales_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "فاتورة مبيعات"
        verbose_name_plural = "فواتير المبيعات"
        ordering = ['-issue_date', '-invoice_number']

    def __str__(self):
        return self.invoice_number

    def get_absolute_url(self):
        return reverse('sales:invoice_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = timezone.now().strftime('%Y%m%d')
            last_invoice = SalesInvoice.objects.filter(invoice_number__startswith=f"INV-{today}-").order_by('invoice_number').last()
            if last_invoice:
                last_id = int(last_invoice.invoice_number.split('-')[-1])
                new_id = last_id + 1
            else:
                new_id = 1
            self.invoice_number = f'INV-{today}-{new_id:04d}'
        super().save(*args, **kwargs)

    def calculate_totals(self):
        items = self.items.all()
        self.subtotal = sum(item.total for item in items if item.total is not None)
        discount = self.discount_amount or Decimal('0.0')
        tax = self.tax_amount or Decimal('0.0')
        self.total = self.subtotal - discount + tax
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
        verbose_name_plural = "بنود الفواتير"

    def save(self, *args, **kwargs):
        base_price = self.unit_price * self.quantity
        discount_amount = base_price * (self.discount_percentage / Decimal('100'))
        self.total = base_price - discount_amount
        super().save(*args, **kwargs)

class Payment(models.Model):
    """
    Handles payments for a sales invoice. An invoice can have multiple payments.
    """
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'نقدي'),
        ('VISA', 'فيزا'),
        ('SMART_WALLET', 'محفظة ذكية'),
        ('INSTAPAY', 'إنستا باي'),
        ('BANK_TRANSFER', 'تحويل بنكي'),
        ('CHEQUE', 'شيك'),
    ]

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='payments', verbose_name="الفاتورة")
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="طريقة الدفع")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    payment_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الدفع")
    transaction_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم المعاملة")
    cheque_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="رقم الشيك")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"

    def __str__(self):
        return f"Payment of {self.amount} for Invoice {self.invoice.invoice_number} via {self.get_method_display()}"
