from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import Supplier, PurchaseOrder, Payment, SupplierRating, SupplierContact, SupplierDocument, PurchaseOrderItem
from warehouses.models import Product, Warehouse


class SupplierForm(forms.ModelForm):
    """نموذج إنشاء وتعديل المورد"""
    
    class Meta:
        model = Supplier
        fields = [
            'name', 'code', 'supplier_type', 'contact_person', 'phone', 
            'email', 'address', 'bank_name', 'account_number', 
            'account_holder_name', 'supported_payment_methods',
            'smart_wallet_phone', 'instapay_identifier',  # Add these fields
            'credit_limit', 'payment_terms_days', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المورد'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'كود المورد'
            }),
            'supplier_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'الشخص المسؤول'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم الهاتف'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'البريد الإلكتروني'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'العنوان'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم البنك'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم الحساب'
            }),
            'account_holder_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم صاحب الحساب'
            }),
            'supported_payment_methods': forms.CheckboxSelectMultiple(),
            'smart_wallet_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم Smart Wallet'
            }),
            'instapay_identifier': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'معرف InstaPay'
            }),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'payment_terms_days': forms.NumberInput(attrs={
                'class': 'form-control'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            # التحقق من عدم تكرار الكود
            queryset = Supplier.objects.filter(code=code)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError('هذا الكود مستخدم بالفعل')
        return code
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # التحقق من صحة البريد الإلكتروني
            queryset = Supplier.objects.filter(email=email)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError('هذا البريد الإلكتروني مستخدم بالفعل')
        return email


class PurchaseOrderForm(forms.ModelForm):
    """نموذج إنشاء وتعديل أمر الشراء"""
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'supplier', 'expected_delivery_date', 'priority', 
            'notes', 'terms_conditions'
        ]
        widgets = {
            'supplier': forms.Select(attrs={
                'class': 'form-control'
            }),
            'expected_delivery_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-control'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات'
            }),
            'terms_conditions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'الشروط والأحكام'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # عرض الموردين النشطين فقط
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)

class PurchaseOrderItemForm(forms.ModelForm):
    """نموذج عنصر أمر الشراء"""
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['product', 'quantity_ordered', 'unit_price', 'notes']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control product-select'
            }),
            'quantity_ordered': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ملاحظات'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)

# Create formset for purchase order items
PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder, 
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True
)

class PurchaseOrderReceiveForm(forms.Form):
    """نموذج استلام أمر الشراء"""
    
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="المخزن"
    )
    
    received_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="تاريخ الاستلام"
    )
    
    quality_check_passed = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="اجتاز فحص الجودة"
    )
    
    delivery_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'ملاحظات الاستلام'
        }),
        label="ملاحظات"
    )

class PurchaseOrderItemReceiveForm(forms.Form):
    """نموذج استلام عنصر أمر الشراء"""
    
    def __init__(self, *args, **kwargs):
        purchase_order = kwargs.pop('purchase_order', None)
        super().__init__(*args, **kwargs)
        
        if purchase_order:
            for item in purchase_order.items.all():
                field_name = f'item_{item.id}_quantity'
                self.fields[field_name] = forms.DecimalField(
                    max_value=item.quantity_pending,
                    min_value=0,
                    decimal_places=2,
                    initial=item.quantity_pending,
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control',
                        'step': '0.01'
                    }),
                    label=f"{item.product.name} (متبقي: {item.quantity_pending})"
                )
                
                quality_field_name = f'item_{item.id}_quality'
                self.fields[quality_field_name] = forms.BooleanField(
                    required=False,
                    initial=True,
                    widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                    label="جودة مقبولة"
                )

class PaymentForm(forms.ModelForm):
    """نموذج إنشاء وتعديل الدفعة"""
    
    class Meta:
        model = Payment
        fields = [
            'supplier', 'purchase_order', 'payment_type', 'payment_method',
            'amount', 'due_date', 'reference_number', 'notes'
        ]
        widgets = {
            'supplier': forms.Select(attrs={
                'class': 'form-control'
            }),
            'purchase_order': forms.Select(attrs={
                'class': 'form-control'
            }),
            'payment_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-control'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم المرجع'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # عرض الموردين النشطين فقط
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        # عرض أوامر الشراء غير المكتملة فقط
        self.fields['purchase_order'].queryset = PurchaseOrder.objects.exclude(
            status__in=['completed', 'cancelled']
        )

# Add this form class to the existing forms

class SupplierRatingForm(forms.ModelForm):
    """نموذج تقييم المورد"""
    
    class Meta:
        model = SupplierRating
        fields = [
            'quality_rating', 'delivery_rating', 'price_rating',
            'service_rating', 'communication_rating', 'comments', 'season'
        ]
        widgets = {
            'quality_rating': forms.Select(
                choices=[(i, f'{i} نجوم') for i in range(1, 6)],
                attrs={'class': 'form-select rating-select', 'data-criteria': 'quality'}
            ),
            'delivery_rating': forms.Select(
                choices=[(i, f'{i} نجوم') for i in range(1, 6)],
                attrs={'class': 'form-select rating-select', 'data-criteria': 'delivery'}
            ),
            'price_rating': forms.Select(
                choices=[(i, f'{i} نجوم') for i in range(1, 6)],
                attrs={'class': 'form-select rating-select', 'data-criteria': 'price'}
            ),
            'service_rating': forms.Select(
                choices=[(i, f'{i} نجوم') for i in range(1, 6)],
                attrs={'class': 'form-select rating-select', 'data-criteria': 'service'}
            ),
            'communication_rating': forms.Select(
                choices=[(i, f'{i} نجوم') for i in range(1, 6)],
                attrs={'class': 'form-select rating-select', 'data-criteria': 'communication'}
            ),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'اكتب تعليقك حول أداء المورد...'
            }),
            'season': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ربيع 2024'
            })
        }
        labels = {
            'quality_rating': 'تقييم الجودة',
            'delivery_rating': 'تقييم التسليم',
            'price_rating': 'تقييم السعر',
            'service_rating': 'تقييم الخدمة',
            'communication_rating': 'تقييم التواصل',
            'comments': 'التعليقات',
            'season': 'الموسم'
        }
        help_texts = {
            'quality_rating': 'قيم جودة المنتجات المستلمة',
            'delivery_rating': 'قيم الالتزام بمواعيد التسليم',
            'price_rating': 'قيم تنافسية الأسعار',
            'service_rating': 'قيم مستوى خدمة العملاء',
            'communication_rating': 'قيم سهولة التواصل والاستجابة',
            'comments': 'أضف أي ملاحظات إضافية',
            'season':'حدد الموسم أو الفترة الزمنية للتقييم'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default season if not provided
        if not self.instance.pk and not self.initial.get('season'):
            from django.utils import timezone
            current_date = timezone.now()
            seasons = {
                1: 'شتاء', 2: 'شتاء', 3: 'ربيع',
                4: 'ربيع', 5: 'ربيع', 6: 'صيف',
                7: 'صيف', 8: 'صيف', 9: 'خريف',
                10: 'خريف', 11: 'خريف', 12: 'شتاء'
            }
            season = seasons.get(current_date.month, 'غير محدد')
            self.initial['season'] = f"{season} {current_date.year}"
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate all ratings are provided
        rating_fields = ['quality_rating', 'delivery_rating', 'price_rating', 
                        'service_rating', 'communication_rating']
        
        for field in rating_fields:
            if not cleaned_data.get(field):
                self.add_error(field, 'هذا الحقل مطلوب')
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Calculate overall rating automatically
        ratings = [
            instance.quality_rating,
            instance.delivery_rating,
            instance.price_rating,
            instance.service_rating,
            instance.communication_rating
        ]
        
        if all(ratings):
            instance.overall_rating = sum(ratings) / len(ratings)
        
        if commit:
            instance.save()
        
        return instance

class QuickRatingForm(forms.Form):
    """نموذج التقييم السريع"""
    overall_rating = forms.ChoiceField(
        choices=[(i, f'{i} نجوم') for i in range(1, 6)],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='التقييم العام'
    )
    comments = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'تعليق سريع (اختياري)...'
        }),
        label='تعليق',
        required=False
    )



class SupplierContactForm(forms.ModelForm):
    """نموذج جهة اتصال المورد"""
    
    class Meta:
        model = SupplierContact
        fields = ['name', 'position', 'phone', 'email', 'is_primary', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'الاسم'
            }),
            'position': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'المنصب'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم الهاتف'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'البريد الإلكتروني'
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات'
            })
        }


class SupplierDocumentForm(forms.ModelForm):
    """نموذج مستند المورد"""
    
    class Meta:
        model = SupplierDocument
        fields = ['document_type', 'title', 'file', 'expiry_date', 'notes']
        widgets = {
            'document_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'عنوان المستند'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات'
            })
        }


class SupplierSearchForm(forms.Form):
    """نموذج البحث في الموردين"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'البحث في الاسم، الكود، أو الشخص المسؤول'
        })
    )
    
    supplier_type = forms.ChoiceField(
        choices=[('', 'جميع الأنواع')] + Supplier.SUPPLIER_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    is_active = forms.ChoiceField(
        choices=[
            ('', 'الكل'),
            ('true', 'نشط'),
            ('false', 'غير نشط')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    min_rating = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': 'أقل تقييم'
        })
    )
    
    max_rating = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': 'أعلى تقييم'
        })
    )


class PurchaseOrderSearchForm(forms.Form):
    """نموذج البحث في أوامر الشراء"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'البحث في رقم الأمر أو اسم المورد'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'جميع الحالات')] + PurchaseOrder.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        empty_label='جميع الموردين',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    priority = forms.ChoiceField(
        choices=[('', 'جميع الأولويات')] + PurchaseOrder.PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


class PaymentSearchForm(forms.Form):
    """نموذج البحث في الدفعات"""
    
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        empty_label='جميع الموردين',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    status = forms.ChoiceField(
        choices=[('', 'جميع الحالات')] + Payment.PAYMENT_STATUS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    payment_type = forms.ChoiceField(
        choices=[('', 'جميع الأنواع')] + Payment.PAYMENT_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    payment_method = forms.ChoiceField(
        choices=[('', 'جميع الطرق')] + Payment.PAYMENT_METHODS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    min_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'أقل مبلغ'
        })
    )
    
    max_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'أعلى مبلغ'
        })
    )


class BulkSupplierUpdateForm(forms.Form):
    """نموذج التحديث المجموعي للموردين"""
    
    ACTION_CHOICES = [
        ('activate', 'تفعيل'),
        ('deactivate', 'إلغاء التفعيل'),
        ('update_payment_terms', 'تحديث شروط الدفع'),
        ('update_credit_limit', 'تحديث حد الائتمان'),
    ]
    
    supplier_ids = forms.CharField(widget=forms.HiddenInput())
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # حقول إضافية للتحديث
    new_payment_terms = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'مدة السداد الجديدة بالأيام'
        })
    )
    
    new_credit_limit = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'حد الائتمان الجديد'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        
        if action == 'update_payment_terms' and not cleaned_data.get('new_payment_terms'):
            raise ValidationError('يجب تحديد مدة السداد الجديدة')
        
        if action == 'update_credit_limit' and not cleaned_data.get('new_credit_limit'):
            raise ValidationError('يجب تحديد حد الائتمان الجديد')
        
        return cleaned_data


class SupplierPerformanceFilterForm(forms.Form):
    """نموذج فلترة أداء الموردين"""
    
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        empty_label='جميع الموردين',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    period_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    period_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    min_completion_rate = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': 'أقل معدل إكمال %'
        })
    )
    
    min_on_time_rate = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': 'أقل معدل التسليم في الوقت %'
        })
    )
    
    min_rating = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': 'أقل تقييم'
        })
    )


class ImportSuppliersForm(forms.Form):
    """نموذج استيراد الموردين من ملف"""
    
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls'
        })
    )
    
    update_existing = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='تحديث الموردين الموجودين بنفس الكود'
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # التحقق من نوع الملف
            allowed_extensions = ['.csv', '.xlsx', '.xls']
            file_extension = file.name.lower().split('.')[-1]
            if f'.{file_extension}' not in allowed_extensions:
                raise ValidationError('نوع الملف غير مدعوم. يرجى استخدام CSV أو Excel')
            
            # التحقق من حجم الملف (أقل من 5 ميجا)
            if file.size > 5 * 1024 * 1024:
                raise ValidationError('حجم الملف كبير جداً. الحد الأقصى 5 ميجابايت')
        
        return file


class QuickSupplierForm(forms.ModelForm):
    """نموذج سريع لإضافة مورد"""
    
    class Meta:
        model = Supplier
        fields = ['name', 'code', 'supplier_type', 'contact_person', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'اسم المورد',
                'required': True
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'كود المورد',
                'required': True
            }),
            'supplier_type': forms.Select(attrs={
                'class': 'form-control form-control-sm',
                'required': True
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'الشخص المسؤول',
                'required': True
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'رقم الهاتف',
                'required': True
            })
        }


class SupplierComparisonForm(forms.Form):
    """نموذج مقارنة الموردين"""
    
    suppliers = forms.ModelMultipleChoiceField(
        queryset=Supplier.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        help_text='اختر الموردين للمقارنة (حد أقصى 5 موردين)'
    )
    
    comparison_criteria = forms.MultipleChoiceField(
        choices=[
            ('rating', 'التقييم'),
            ('total_orders', 'عدد الأوامر'),
            ('total_amount', 'إجمالي المبلغ'),
            ('completion_rate', 'معدل الإكمال'),
            ('on_time_delivery', 'التسليم في الوقت'),
            ('credit_limit', 'حد الائتمان'),
            ('payment_terms', 'شروط الدفع'),
        ],
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        initial=['rating', 'total_orders', 'completion_rate']
    )
    
    period_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    period_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    def clean_suppliers(self):
        suppliers = self.cleaned_data.get('suppliers')
        if suppliers and len(suppliers) > 5:
            raise ValidationError('لا يمكن مقارنة أكثر من 5 موردين في المرة الواحدة')
        if suppliers and len(suppliers) < 2:
            raise ValidationError('يجب اختيار مورد واحد على الأقل للمقارنة')
        return suppliers


# Custom Field Types
class MultipleChoiceField(forms.MultipleChoiceField):
    """حقل اختيار متعدد مخصص"""
    
    def __init__(self, *args, **kwargs):
        self.max_choices = kwargs.pop('max_choices', 0)
        super().__init__(*args, **kwargs)
    
    def clean(self, value):
        if not value and self.required:
            raise ValidationError(self.error_messages['required'])
        
        if value and self.max_choices and len(value) > self.max_choices:
            raise ValidationError(
                f'لا يمكن اختيار أكثر من {self.max_choices} عناصر'
            )
        
        return super().clean(value)


class DateRangeField(forms.Field):
    """حقل نطاق التاريخ"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'من تاريخ - إلى تاريخ'
        }))
        super().__init__(*args, **kwargs)
    
    def clean(self, value):
        if not value:
            return None
        
        try:
            start_date, end_date = value.split(' - ')
            start_date = datetime.strptime(start_date.strip(), '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date.strip(), '%Y-%m-%d').date()
            
            if start_date > end_date:
                raise ValidationError('تاريخ البداية يجب أن يكون قبل تاريخ النهاية')
            
            return {'start': start_date, 'end': end_date}
        except ValueError:
            raise ValidationError('تنسيق التاريخ غير صحيح')


# Form Mixins
class AjaxFormMixin:
    """خليط للنماذج التي تدعم AJAX"""
    
    def __init__(self, *args, **kwargs):
        self.is_ajax = kwargs.pop('is_ajax', False)
        super().__init__(*args, **kwargs)
        
        if self.is_ajax:
            for field in self.fields.values():
                if 'class' in field.widget.attrs:
                    field.widget.attrs['class'] += ' ajax-field'
                else:
                    field.widget.attrs['class'] = 'ajax-field'


class TimestampMixin:
    """خليط لإضافة معلومات الوقت"""
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if not instance.pk:
            instance.created_at = timezone.now()
        instance.updated_at = timezone.now()
        
        if commit:
            instance.save()
        
        return instance
