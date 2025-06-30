from django import forms
from .models import Setting

class BaseSettingsForm(forms.Form):
    """
    A base form that dynamically loads initial values from the Setting model
    and provides a consistent save method.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            # Skip file fields as they don't have a simple value to load
            if isinstance(self.fields[field_name], forms.FileField):
                continue
            try:
                setting = Setting.objects.get(key=field_name)
                # Handle boolean fields which are stored as strings 'True'/'False'
                if isinstance(self.fields[field_name], forms.BooleanField):
                    self.fields[field_name].initial = setting.value.lower() in ('true', '1')
                else:
                    self.fields[field_name].initial = setting.value
            except Setting.DoesNotExist:
                pass

    def save(self):
        """
        Saves the form data back to the Setting model in the database.
        File fields are handled separately in the view.
        """
        for key, value in self.cleaned_data.items():
            # Skip file fields as they are handled in the view
            if isinstance(self.fields[key], forms.FileField):
                continue
            
            if isinstance(value, bool):
                value_to_save = 'True' if value else 'False'
            else:
                value_to_save = str(value)

            Setting.objects.update_or_create(
                key=key,
                defaults={'value': value_to_save}
            )

class GeneralSettingsForm(BaseSettingsForm):
    """
    A form for managing the site's main settings.
    """
    site_name = forms.CharField(label="اسم الموقع", required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    maintenance_mode = forms.BooleanField(label="وضع الصيانة", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    contact_email = forms.EmailField(label="البريد الإلكتروني للتواصل", required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

class AppearanceSettingsForm(BaseSettingsForm):
    """
    A form for managing the site's visual appearance settings.
    """
    site_logo = forms.ImageField(
        label="شعار الموقع (يفضل أن يكون شفافاً)",
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    sidebar_bg_color = forms.CharField(
        label="لون خلفية الشريط الجانبي",
        required=False,
        widget=forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color', 'title': 'اختر لون الخلفية'})
    )
    sidebar_text_color = forms.CharField(
        label="لون نص الشريط الجانبي",
        required=False,
        widget=forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color', 'title': 'اختر لون النص'})
    )

class ImportBackupForm(forms.Form):
    """
    A form for uploading a backup file (.json or .db) for restoration.
    """
    backup_file = forms.FileField(
        label="ملف النسخ الاحتياطي (.db أو .json)",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.db,.json'})
    )
