from django.db import models

class Setting(models.Model):
    """
    A model to store application settings as key-value pairs.
    This provides a flexible way to manage site-wide configurations from the admin interface.
    """
    key = models.CharField(max_length=100, unique=True, primary_key=True, verbose_name="المفتاح")
    value = models.TextField(blank=True, verbose_name="القيمة")
    description = models.TextField(blank=True, verbose_name="الوصف")

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = "إعداد"
        verbose_name_plural = "الإعدادات"

