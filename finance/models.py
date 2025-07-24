# finance/models.py

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, Q, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
import uuid

class AccountCategory(models.Model):
    """
    Categories for the Chart of Accounts (e.g., Assets, Liabilities, Equity, Revenue, Expenses).
    This provides the high-level structure for financial reports.
    """
    CATEGORY_TYPES = [
        ('asset', 'الأصول'),
        ('liability', 'الخصوم'),
        ('equity', 'حقوق الملكية'),
        ('revenue', 'الإيرادات'),
        ('expense', 'المصروفات'),
    ]
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الفئة")
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPES, verbose_name="نوع الفئة")
    description = models.TextField(blank=True, verbose_name="الوصف")

    class Meta:
        verbose_name = "فئة حساب"
        verbose_name_plural = "فئات الحسابات"
        ordering = ['category_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"

class Account(models.Model):
    """
    An individual account in the Chart of Accounts.
    Can be linked to a specific entity like a Manufacturer, Customer, or be a general account.
    The GenericForeignKey allows this model to be flexibly linked to any other model in your ERP.
    """
    category = models.ForeignKey(AccountCategory, on_delete=models.PROTECT, related_name='accounts', verbose_name="الفئة")
    name = models.CharField(max_length=200, verbose_name="اسم الحساب")
    code = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name="الكود")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    # Generic Foreign Key to link this account to another object (e.g., ExternalManufacturer)
    owner_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    # CORRECTED: Changed from UUIDField to PositiveIntegerField to match default Django PKs
    owner_object_id = models.PositiveIntegerField(null=True, blank=True)
    owner = GenericForeignKey('owner_content_type', 'owner_object_id')

    class Meta:
        verbose_name = "حساب"
        verbose_name_plural = "الحسابات (دليل الحسابات)"
        ordering = ['category', 'name']
        unique_together = ('owner_content_type', 'owner_object_id')

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def balance(self):
        """
        Calculates the current balance of the account based on its type.
        - Assets & Expenses: increase with debits.
        - Liabilities, Equity & Revenue: increase with credits.
        """
        aggregation = self.transaction_details.aggregate(
            total_debit=Coalesce(Sum('debit'), Decimal('0.0')),
            total_credit=Coalesce(Sum('credit'), Decimal('0.0'))
        )
        total_debit = aggregation['total_debit']
        total_credit = aggregation['total_credit']

        if self.category.category_type in ['asset', 'expense']:
            return total_debit - total_credit
        else: # liability, equity, revenue
            return total_credit - total_debit

class Transaction(models.Model):
    """
    Represents a single, balanced financial transaction (a journal entry).
    It acts as a header for multiple TransactionDetail lines.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=255, verbose_name="الوصف")
    date = models.DateField(default=timezone.now, verbose_name="التاريخ")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="تم إنشاؤه بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="توقيت الإنشاء")

    # Generic Foreign Key to link this transaction to a source document (e.g., Invoice, Payment)
    source_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_document = GenericForeignKey('source_content_type', 'source_object_id')

    class Meta:
        verbose_name = "حركة مالية"
        verbose_name_plural = "الحركات المالية (دفتر اليومية)"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"حركة بتاريخ {self.date}: {self.description}"

    @property
    def total_debit(self):
        return self.details.aggregate(total=Sum('debit'))['total'] or Decimal('0.00')

    @property
    def total_credit(self):
        return self.details.aggregate(total=Sum('credit'))['total'] or Decimal('0.00')

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit

class TransactionDetail(models.Model):
    """
    A single line within a Transaction, representing either a debit or a credit to an account.
    """
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='details', verbose_name="الحركة المالية")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transaction_details', verbose_name="الحساب")
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="مدين")
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="دائن")

    class Meta:
        verbose_name = "تفاصيل الحركة"
        verbose_name_plural = "تفاصيل الحركات"
        ordering = ['transaction', 'debit']

    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("لا يمكن أن يكون للحركة قيمة في المدين والدائن في نفس الوقت.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("يجب أن يكون للحركة قيمة في المدين أو الدائن.")

    def __str__(self):
        if self.debit > 0:
            return f"{self.account.name} مدين بـ {self.debit}"
        return f"{self.account.name} دائن بـ {self.credit}"

class Invoice(models.Model):
    """
    Represents both a sales invoice (to a customer) and a bill (from a vendor).
    The 'recipient' GenericForeignKey determines who it's for.
    """
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('sent', 'مرسلة'),
        ('received', 'مستلمة'), # For vendor bills
        ('paid', 'مدفوعة بالكامل'),
        ('partial', 'مدفوعة جزئياً'),
        ('void', 'ملغاة'),
    ]
    invoice_number = models.CharField(max_length=50, unique=True, blank=True, verbose_name="رقم الفاتورة/الوصل")
    issue_date = models.DateField(default=timezone.now, verbose_name="تاريخ الإصدار")
    due_date = models.DateField(verbose_name="تاريخ الاستحقاق")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ الإجمالي")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="المبلغ المدفوع")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name="الحالة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    # Generic Foreign Key for the recipient (Customer or ExternalManufacturer)
    recipient_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    recipient_object_id = models.PositiveIntegerField()
    recipient = GenericForeignKey('recipient_content_type', 'recipient_object_id')

    class Meta:
        verbose_name = "فاتورة / وصل"
        verbose_name_plural = "الفواتير والوصولات"
        ordering = ['-issue_date']

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today_str = timezone.now().strftime('%Y%m%d')
            last_invoice = Invoice.objects.filter(invoice_number__startswith=f"INV-{today_str}").last()
            if last_invoice:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                self.invoice_number = f"INV-{today_str}-{last_num + 1:04d}"
            else:
                self.invoice_number = f"INV-{today_str}-0001"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"فاتورة {self.invoice_number} لـ {self.recipient}"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

class Payment(models.Model):
    """
    A payment made or received against an invoice.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', verbose_name="الفاتورة")
    payment_date = models.DateField(default=timezone.now, verbose_name="تاريخ الدفع")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ")
    payment_method = models.CharField(max_length=50, verbose_name="طريقة الدفع", choices=[('cash', 'نقدي'), ('bank', 'تحويل بنكي'), ('cheque', 'شيك')])
    reference = models.CharField(max_length=100, blank=True, verbose_name="مرجع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="تم إنشاؤه بواسطة")

    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"
        ordering = ['-payment_date']

    def __str__(self):
        return f"دفعة بقيمة {self.amount} للفاتورة {self.invoice.invoice_number}"

class Expense(models.Model):
    """
    Represents a simple, direct expense not necessarily tied to a bill.
    (e.g., buying office supplies with cash).
    """
    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='expenses', limit_choices_to={'category__category_type': 'expense'}, verbose_name="حساب المصروف")
    source_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='source_of_expenses', limit_choices_to={'category__category_type': 'asset'}, verbose_name="حساب المصدر (نقدي/بنك)")
    description = models.CharField(max_length=255, verbose_name="الوصف")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ")
    expense_date = models.DateField(default=timezone.now, verbose_name="تاريخ المصروف")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="تم إنشاؤه بواسطة")
    
    class Meta:
        verbose_name = "مصروف"
        verbose_name_plural = "المصروفات"
        ordering = ['-expense_date']

    def __str__(self):
        return f"مصروف: {self.description} بقيمة {self.amount}"
