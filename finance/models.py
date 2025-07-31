# finance/models.py

from django.db import models
from django.urls import reverse
from decimal import Decimal
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# --- FIX: Import ExternalManufacturer to link it to transactions ---
# Make sure the production app is listed before the finance app in INSTALLED_APPS
# if you encounter circular import errors.
from production.models import ExternalManufacturer


class Account(models.Model):
    """
    Represents a financial account in the factory, like a treasury or expense account.
    """
    ACCOUNT_TYPES = (
        ('ASSET', 'أصل (خزينة/بنك)'),
        ('LIABILITY', 'التزام (مورد/مصنع)'),
        ('EXPENSE', 'مصروفات'),
        ('REVENUE', 'إيرادات'),
    )
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الحساب")
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="الرصيد الحالي")
    
    # --- NEW: Added account type and a link to manufacturer ---
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='ASSET', verbose_name="نوع الحساب")
    manufacturer = models.OneToOneField(
        ExternalManufacturer, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='finance_account',
        verbose_name="المصنع الخارجي المرتبط"
    )

    class Meta:
        verbose_name = "حساب"
        verbose_name_plural = "الحسابات"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"

    def get_absolute_url(self):
        return reverse('finance:account_list')


class Transaction(models.Model):
    """
    Records a financial transaction.
    """
    # --- NEW: Added new transaction types for manufacturing ---
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'إيداع'),
        ('WITHDRAWAL', 'سحب'),
        ('TRANSFER', 'تحويل'),
        ('MANUFACTURING_DEBT', 'تسجيل تكلفة تصنيع'), # Debt created when receiving goods
        ('MANUFACTURER_PAYMENT', 'دفعة لمصنع'),      # Payment made to manufacturer
    )

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transactions', verbose_name="الحساب")
    
    to_account = models.ForeignKey(
        Account, 
        on_delete=models.PROTECT, 
        related_name='transfers_to', 
        null=True, 
        blank=True, 
        verbose_name="إلى حساب"
    )

    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="نوع الحركة")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ")
    description = models.TextField(verbose_name="السبب / الوصف")
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="مرجع (اختياري)")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ والوقت")

    # --- NEW: Generic relation to link transaction to its source (e.g., AssemblyProcess) ---
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = "حركة مالية"
        verbose_name_plural = "الحركات المالية"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_type_display()} - {self.amount} - {self.account.name}"

