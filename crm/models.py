from django.db import models
from django.conf import settings
from phonenumber_field.modelfields import PhoneNumberField
from django.urls import reverse

class Customer(models.Model):
    """
    Represents a customer, which can be an individual or a company.
    """
    CUSTOMER_TYPE_CHOICES = [
        ('INDIVIDUAL', 'فرد'),
        ('COMPANY', 'شركة'),
    ]

    # Core Information
    name = models.CharField(max_length=255, verbose_name="اسم العميل")
    customer_type = models.CharField(max_length=10, choices=CUSTOMER_TYPE_CHOICES, default='INDIVIDUAL', verbose_name="نوع العميل")
    phone_number = PhoneNumberField(verbose_name="رقم الهاتف", help_text="مثال: +201012345678")
    # MODIFIED: Email is now optional
    email = models.EmailField(max_length=255, blank=True, null=True, verbose_name="البريد الإلكتروني")
    
    # Address Information
    address_line_1 = models.CharField(max_length=255, blank=True, verbose_name="العنوان (سطر 1)")
    address_line_2 = models.CharField(max_length=255, blank=True, verbose_name="العنوان (سطر 2)")
    city = models.CharField(max_length=100, blank=True, verbose_name="المدينة")
    governorate = models.CharField(max_length=100, blank=True, verbose_name="المحافظة")
    country = models.CharField(max_length=100, default="Egypt", verbose_name="الدولة")

    # Company-Specific Information
    company_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="اسم الشركة")
    tax_id = models.CharField(max_length=50, blank=True, verbose_name="الرقم الضريبي")

    # Additional Information
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_customers', verbose_name="تم الإنشاء بواسطة")

    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
        ordering = ['-created_at']

    def __str__(self):
        return self.name or self.company_name

    def get_absolute_url(self):
        return reverse('crm:customer_detail', kwargs={'pk': self.pk})

class Interaction(models.Model):
    """
    Logs an interaction (e.g., call, meeting, email) with a customer.
    """
    INTERACTION_TYPE_CHOICES = [
        ('CALL', 'مكالمة'),
        ('EMAIL', 'بريد إلكتروني'),
        ('MEETING', 'اجتماع'),
        ('NOTE', 'ملاحظة'),
        ('WHATSAPP', 'واتساب'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions', verbose_name="العميل")
    interaction_type = models.CharField(max_length=10, choices=INTERACTION_TYPE_CHOICES, verbose_name="نوع التفاعل")
    interaction_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التفاعل")
    summary = models.TextField(verbose_name="ملخص التفاعل")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="المستخدم")

    class Meta:
        verbose_name = "تفاعل"
        verbose_name_plural = "التفاعلات"
        ordering = ['-interaction_date']

    def __str__(self):
        return f"{self.get_interaction_type_display()} with {self.customer.name} on {self.interaction_date.strftime('%Y-%m-%d')}"
