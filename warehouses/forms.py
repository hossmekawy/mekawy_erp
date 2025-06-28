from django import forms
from django.contrib.auth import get_user_model
from .models import Category, Unit, UnitConversion, Warehouse, Product, StockItem, StockMovement, StockTransfer

User = get_user_model()

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل اسم التصنيف'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'أدخل وصف التصنيف (اختياري)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise forms.ValidationError('اسم التصنيف مطلوب')
        # Check for duplicate names (excluding current instance if editing)
        queryset = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise forms.ValidationError('يوجد تصنيف بهذا الاسم بالفعل')
        
        return name

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'code', 'type', 'description', 'manager', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل اسم المخزن'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل كود المخزن'
            }),
            'type': forms.Select(attrs={'class': 'form-select'}),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'أدخل وصف المخزن (اختياري)'
            }),
            'manager': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Assuming you have a way to identify managers. If not, this can be changed.
        self.fields['manager'].queryset = User.objects.filter(is_staff=True, is_active=True)
        self.fields['manager'].required = False
        self.fields['manager'].empty_label = "--- اختر مديراً ---"
class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ['warehouse', 'product', 'quantity', 'reserved_quantity', 'location']
        widgets = {
            'warehouse': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'product': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'required': True
            }),
            'reserved_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'value': '0'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: الرف A - المستوى 2 - الصندوق 15'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active warehouses and products
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        
        # Set labels
        self.fields['warehouse'].label = 'المخزن'
        self.fields['product'].label = 'المنتج'
        self.fields['quantity'].label = 'الكمية الإجمالية'
        self.fields['reserved_quantity'].label = 'الكمية المحجوزة'
        self.fields['location'].label = 'الموقع'
    
    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        reserved_quantity = cleaned_data.get('reserved_quantity', 0)
        
        if warehouse and product:
            # Check if stock item already exists for this warehouse-product combination
            existing = StockItem.objects.filter(warehouse=warehouse, product=product)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('يوجد عنصر مخزون لهذا المنتج في هذا المخزن بالفعل')
        
        if quantity is not None and reserved_quantity is not None:
            if reserved_quantity > quantity:
                raise forms.ValidationError('الكمية المحجوزة لا يمكن أن تكون أكبر من الكمية الإجمالية')
        
        return cleaned_data

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'code', 'barcode', 'category', 'product_type', 'unit', 
                 'cost_price', 'selling_price', 'min_stock_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المنتج'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود المنتج'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الباركود'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'min_stock_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ['stock_item', 'movement_type', 'quantity', 'reference_number', 'notes']
        widgets = {
            'stock_item': forms.Select(attrs={'class': 'form-select'}),
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم المرجع'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'ملاحظات'}),
        }

class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['from_warehouse', 'to_warehouse', 'product', 'quantity', 'reason']
        widgets = {
            'from_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'سبب التحويل'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        from_warehouse = cleaned_data.get('from_warehouse')
        to_warehouse = cleaned_data.get('to_warehouse')
        
        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            raise forms.ValidationError('لا يمكن التحويل من نفس المخزن إلى نفسه')
        
        return cleaned_data
    
# Add these new forms to your existing forms.py

class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'symbol', 'is_base_unit', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل اسم الوحدة'
            }),
            'symbol': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل رمز الوحدة'
            }),
            'is_base_unit': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise forms.ValidationError('اسم الوحدة مطلوب')
        
        # Check for duplicate names (excluding current instance if editing)
        queryset = Unit.objects.filter(name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise forms.ValidationError('يوجد وحدة بهذا الاسم بالفعل')
        
        return name

class UnitConversionForm(forms.ModelForm):
    class Meta:
        model = UnitConversion
        fields = ['from_unit', 'to_unit', 'conversion_factor']
        widgets = {
            'from_unit': forms.Select(attrs={
                'class': 'form-select'
            }),
            'to_unit': forms.Select(attrs={
                'class': 'form-select'
            }),
            'conversion_factor': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001',
                'min': '0.0001',
                'placeholder': 'مثال: 48 (1 شيكارة = 48 قطعة)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['from_unit'].queryset = Unit.objects.filter(is_active=True)
        self.fields['to_unit'].queryset = Unit.objects.filter(is_active=True)
        
        # Set labels
        self.fields['from_unit'].label = 'من الوحدة'
        self.fields['to_unit'].label = 'إلى الوحدة'
        self.fields['conversion_factor'].label = 'معامل التحويل'
    
    def clean(self):
        cleaned_data = super().clean()
        from_unit = cleaned_data.get('from_unit')
        to_unit = cleaned_data.get('to_unit')
        
        if from_unit and to_unit:
            if from_unit == to_unit:
                raise forms.ValidationError('لا يمكن أن تكون الوحدة المصدر والهدف نفسها')
            
            # Check if conversion already exists
            existing = UnitConversion.objects.filter(
                from_unit=from_unit, to_unit=to_unit
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('يوجد تحويل لهذه الوحدات بالفعل')
        
        return cleaned_data

# Update ProductForm to use the new Unit model
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'code', 'barcode', 'category', 'product_type', 'unit', 
                 'cost_price', 'selling_price', 'min_stock_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المنتج'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود المنتج'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الباركود'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),  # Updated to use Unit model
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'min_stock_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].queryset = Unit.objects.filter(is_active=True)
