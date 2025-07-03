from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import User, UserProfile

class CustomAuthenticationForm(AuthenticationForm):
    # Change from EmailField to CharField to accept username or email
    username = forms.CharField(
        label="اسم المستخدم أو البريد الإلكتروني",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'اسم المستخدم أو البريد الإلكتروني',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة المرور',
            'id': 'id_password'  # Add ID for the toggle button script
        })
    )
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # The custom backend will handle checking both username and email.
            self.user_cache = authenticate(
                self.request, 
                username=username, 
                password=password
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    'اسم المستخدم/البريد الإلكتروني أو كلمة المرور غير صحيحة.',
                    code='invalid_login'
                )
            else:
                self.confirm_login_allowed(self.user_cache)
        
        return self.cleaned_data

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        label="البريد الإلكتروني",
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'البريد الإلكتروني'})
    )
    first_name = forms.CharField(
        label="الاسم الأول",
        max_length=30, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'})
    )
    last_name = forms.CharField(
        label="الاسم الأخير",
        max_length=30, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأخير'})
    )
    username = forms.CharField(
        label="اسم المستخدم",
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستخدم'})
    )
    phone = forms.CharField(
        label="رقم الهاتف",
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'})
    )
    role = forms.ChoiceField(
        label="الدور",
        choices=User.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    department = forms.CharField(
        label="القسم",
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'القسم'})
    )
    password1 = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'كلمة المرور'})
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'تأكيد كلمة المرور'})
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'role', 'department')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('هذا البريد الإلكتروني مستخدم بالفعل.')
        return email

class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="الاسم الأول", max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label="الاسم الأخير", max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label="البريد الإلكتروني", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(label="رقم الهاتف", max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    department = forms.CharField(label="القسم", max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    profile_picture = forms.ImageField(label="الصورة الشخصية", required=False, widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}))

    class Meta:
        model = User
        fields = ['profile_picture', 'first_name', 'last_name', 'email', 'phone', 'department']

class UserEditForm(forms.ModelForm):
    first_name = forms.CharField(label="الاسم الأول", max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label="الاسم الأخير", max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label="البريد الإلكتروني", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(label="رقم الهاتف", max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(label="الدور", choices=User.ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    department = forms.CharField(label="القسم", max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    is_active = forms.BooleanField(label="الحساب نشط", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'role', 'department', 'is_active']

class UserProfileSettingsForm(forms.ModelForm):
    bio = forms.CharField(
        label="نبذة تعريفية",
        max_length=500, required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'نبذة عنك...'})
    )
    location = forms.CharField(
        label="الموقع",
        max_length=30, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الموقع'})
    )
    birth_date = forms.DateField(
        label="تاريخ الميلاد",
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    theme_preference = forms.ChoiceField(
        label="تفضيل المظهر",
        choices=[('light', 'فاتح'), ('dark', 'داكن')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    language_preference = forms.ChoiceField(
        label="تفضيل اللغة",
        choices=[('en', 'English'), ('ar', 'العربية')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = UserProfile
        fields = ['bio', 'location', 'birth_date', 'theme_preference', 'language_preference']
