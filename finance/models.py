# finance/models.py

from django.db import models
from django.urls import reverse
from decimal import Decimal

class Account(models.Model):
    """
    Represents a financial account in the factory, like a treasury or expense account.
    يمثل حسابًا ماليًا في المصنع، مثل الخزينة أو حساب المصاريف.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الحساب")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="الرصيد الحالي")

    class Meta:
        verbose_name = "حساب"
        verbose_name_plural = "الحسابات"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('finance:account_list')


class Transaction(models.Model):
    """
    Records a financial transaction (Deposit, Withdrawal, Transfer).
    تسجيل حركة مالية (إيداع، سحب، تحويل).
    """
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'إيداع'),        # In
        ('WITHDRAWAL', 'سحب'),   # Out
        ('TRANSFER', 'تحويل'),     # Between accounts
    )

    # The primary account for the transaction. For transfers, this is the "from" account.
    # الحساب الرئيسي للحركة. في حالة التحويل، يكون هذا هو الحساب "من".
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transactions', verbose_name="الحساب")
    
    # Only used for transfers. The account receiving the money.
    # يستخدم فقط للتحويلات. الحساب الذي يستقبل الأموال.
    to_account = models.ForeignKey(
        Account, 
        on_delete=models.PROTECT, 
        related_name='transfers_to', 
        null=True, 
        blank=True, 
        verbose_name="إلى حساب"
    )

    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES, verbose_name="نوع الحركة")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ")
    description = models.TextField(verbose_name="السبب / الوصف")
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="مرجع (اختياري)")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ والوقت")

    class Meta:
        verbose_name = "حركة مالية"
        verbose_name_plural = "الحركات المالية"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_type_display()} - {self.amount} - {self.account.name}"