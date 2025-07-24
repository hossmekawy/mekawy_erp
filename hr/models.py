from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime

User = get_user_model()

class Department(models.Model):
    """Model to store company departments."""
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم القسم")

    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"

    def __str__(self):
        return self.name

class Employee(models.Model):
    """Model to store employee data."""
    GENDER_CHOICES = (
        ('Male', 'ذكر'),
        ('Female', 'أنثى'),
    )
    
    # It's good practice to link your employee to a Django user if they need to log in
    # If not, you can remove this field.
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المستخدم المرتبط")
    
    employee_id = models.CharField(max_length=20, unique=True, verbose_name="كود الموظف (على جهاز البصمة)")
    full_name = models.CharField(max_length=200, verbose_name="الاسم بالكامل")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="القسم")
    job_title = models.CharField(max_length=100, verbose_name="المسمى الوظيفي")
    phone_number = models.CharField(max_length=15, blank=True, verbose_name="رقم الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    address = models.TextField(blank=True, verbose_name="العنوان")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, verbose_name="الجنس")
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الميلاد")
    hire_date = models.DateField(verbose_name="تاريخ التعيين")
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الراتب" , null=True, blank=True,)
    
    # Work schedule
    work_start_time = models.TimeField(default=datetime.time(8, 0), verbose_name="وقت بدء العمل")
    work_end_time = models.TimeField(default=datetime.time(17, 0), verbose_name="وقت انتهاء العمل")

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    photo = models.ImageField(upload_to='employee_photos/', null=True, blank=True, verbose_name="صورة الموظف")
    id_face_image = models.ImageField(upload_to='employee_ids/', null=True, blank=True, verbose_name="صورة وجه البطاقة")
    id_back_image = models.ImageField(upload_to='employee_ids/', null=True, blank=True, verbose_name="صورة ظهر البطاقة")

    class Meta:
        verbose_name = "موظف"
        verbose_name_plural = "الموظفين"
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

class Attendance(models.Model):
    """Model to store daily attendance records."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="الموظف")
    date = models.DateField(verbose_name="التاريخ")
    check_in = models.DateTimeField(null=True, blank=True, verbose_name="وقت الحضور")
    check_out = models.DateTimeField(null=True, blank=True, verbose_name="وقت الانصراف")

    class Meta:
        verbose_name = "حضور وانصراف"
        verbose_name_plural = "سجلات الحضور والانصراف"
        # Ensure only one record per employee per day
        unique_together = ('employee', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee.full_name} - {self.date}"

    @property
    def work_duration(self):
        """Calculates the duration of work for the day."""
        if self.check_in and self.check_out:
            duration = self.check_out - self.check_in
            return duration
        return None
