from django.contrib.auth.models import AbstractUser
from django.db import models
from PIL import Image

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'مدير النظام'),
        ('manager', 'مدير'),
        ('warehouse_manager', 'مدير المخازن'),
        ('warehouse_employee', 'موظف مخازن'),
        ('production_manager', 'مدير الإنتاج'),
        ('accountant', 'محاسب'),
        ('employee', 'موظف'),
        ('viewer', 'مشاهد فقط'),
    ]
    
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم الهاتف")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee', verbose_name="الدور")
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name="القسم")
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True, verbose_name="الصورة الشخصية")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
    class Meta:
        db_table = 'users_user'
        verbose_name = 'مستخدم'
        verbose_name_plural = 'المستخدمون'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
    def save(self, *args, **kwargs):
        # This logic ensures that the 'admin' role and superuser status are always in sync.
        if self.role == 'admin':
            self.is_staff = True
            self.is_superuser = True
        # This handles superusers created via the createsuperuser command
        elif self.is_superuser:
            self.role = 'admin'
        
        super().save(*args, **kwargs)
        
        # Resize profile picture after saving the model
        if self.profile_picture and os.path.exists(self.profile_picture.path):
            try:
                img = Image.open(self.profile_picture.path)
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(self.profile_picture.path)
            except (IOError, FileNotFoundError):
                # This can happen if the file is not a valid image or doesn't exist.
                # You might want to log this error.
                pass
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_role_display_ar(self):
        return self.get_role_display()
    
    @property
    def initials(self):
        """
        Returns the user's initials.
        For "حسام علي", it returns "ح ع".
        """
        if self.first_name and self.last_name:
            return f"{self.first_name[0]} {self.last_name[0]}"
        elif self.first_name:
            return self.first_name[0]
        elif self.username:
            return self.username[0]
        return "?"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, verbose_name="نبذة تعريفية")
    location = models.CharField(max_length=30, blank=True, verbose_name="الموقع")
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الميلاد")
    theme_preference = models.CharField(
        max_length=10,
        choices=[('light', 'فاتح'), ('dark', 'داكن')],
        default='light',
        verbose_name="تفضيل المظهر"
    )
    language_preference = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('ar', 'العربية')],
        default='ar',
        verbose_name="تفضيل اللغة"
    )
    
    def __str__(self):
        return f"ملف {self.user.username} الشخصي"
