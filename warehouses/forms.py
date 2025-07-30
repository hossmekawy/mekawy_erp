from django import forms
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from .models import Category, Unit, UnitConversion, Warehouse, Product, StockItem, StockMovement, StockTransfer

User = get_user_model()

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'أدخل اسم التصنيف، مثال: بنطلونات'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'أدخل وصف قصير للتصنيف (اختياري)'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
        # --- FIX: Added 'code' to the fields list ---
        fields = ['name', 'code', 'location', 'warehouse_type', 'description', 'manager', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: مخزن الخامات الرئيسي'
            }),
            # --- FIX: Added widget for the new 'code' field ---
            'code': forms.TextInput(attrs={
                'class': 'form-control bg-gray-100', # Added background color for readonly visual cue
                'placeholder': 'سيتم إنشاؤه تلقائيًا عند الحفظ',
                'readonly': True 
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: المنطقة الصناعية، المنصورة'
            }),
            'warehouse_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'أدخل أي تفاصيل إضافية عن المخزن (اختياري)'
            }),
            'manager': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['manager'].queryset = User.objects.filter(is_staff=True, is_active=True)
        self.fields['manager'].required = False
        # --- FIX: Make the code field not required by the form ---
        self.fields['code'].required = False


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ['warehouse', 'product', 'quantity', 'reserved_quantity', 'location']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'الكمية المتاحة حالياً'
            }),
            'reserved_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'الكمية المحجوزة لأوامر الإنتاج'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: رف A-1، صندوق 5'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter dropdowns to only show active options
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        
        # Set Arabic labels for clarity
        self.fields['warehouse'].label = 'المخزن'
        self.fields['product'].label = 'المنتج'
        self.fields['quantity'].label = 'الكمية الإجمالية'
        self.fields['reserved_quantity'].label = 'الكمية المحجوزة'
        self.fields['location'].label = 'الموقع داخل المخزن'
    
    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        reserved_quantity = cleaned_data.get('reserved_quantity', 0)
        
        # On create, check if a stock item already exists for this product-warehouse combo
        if not self.instance.pk:
            if warehouse and product:
                if StockItem.objects.filter(warehouse=warehouse, product=product).exists():
                    raise forms.ValidationError('يوجد عنصر مخزون لهذا المنتج في هذا المخزن بالفعل. يرجى تعديل العنصر الموجود بدلاً من إضافة جديد.')

        # Ensure reserved quantity is not greater than total quantity
        if quantity is not None and reserved_quantity is not None:
            if reserved_quantity > quantity:
                raise forms.ValidationError('الكمية المحجوزة لا يمكن أن تكون أكبر من الكمية الإجمالية')
        
        return cleaned_data

# --- NEW FORM FOR UPDATING ---
class StockItemUpdateForm(forms.ModelForm):
    """
    A simplified form for UPDATING an existing stock item.
    Only allows changing the quantity and location.
    """
    class Meta:
        model = StockItem
        fields = ['quantity', 'reserved_quantity', 'location']
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
                'required': True
            }),
            'reserved_quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'مثال: الرف A - المستوى 2'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity'].label = 'الكمية الإجمالية الجديدة'
        self.fields['reserved_quantity'].label = 'الكمية المحجوزة الجديدة'
        self.fields['location'].label = 'الموقع الجديد في المخزن'

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity')
        reserved_quantity = cleaned_data.get('reserved_quantity', 0)
        
        if quantity is not None and reserved_quantity is not None:
            if reserved_quantity > quantity:
                raise forms.ValidationError('الكمية المحجوزة لا يمكن أن تكون أكبر من الكمية الإجمالية.')
        
        return cleaned_data


try:
    from production.models import SizeGroup
    PRODUCTION_APP_AVAILABLE = True
except (ImportError, AppRegistryNotReady):
    PRODUCTION_APP_AVAILABLE = False


from django import forms
from django.core.exceptions import AppRegistryNotReady
from .models import Product, Unit, Category

# It's assumed your production app might not always be installed
# This makes the form more robust.
try:
    from production.models import SizeGroup
    PRODUCTION_APP_AVAILABLE = True
except (ImportError, AppRegistryNotReady):
    PRODUCTION_APP_AVAILABLE = False

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Define all fields that could possibly be used in the form
        fields = [
            'name', 'code', 'barcode', 'category', 'product_type', 
            'cost_price', 'selling_price', 'min_stock_level', 
            'unit',  'is_active',
            'colors', 'width', 'quality_grade', 
            'size_groups', 'fabric_quantity_per_piece'
        ]
        widgets = {
            # General Fields
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'يتم التوليد تلقائياً إذا ترك فارغاً'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_product_type'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_stock_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            
            # Unit fields
            'unit': forms.Select(attrs={'class': 'form-select'}), # Old system
            
            
            # Textile fields
            'width': forms.NumberInput(attrs={'class': 'form-control'}),
            'colors': forms.TextInput(attrs={'class': 'form-control'}),
            'quality_grade': forms.Select(attrs={'class': 'form-select'}),
            
            # Finished Product fields
            'selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'size_groups': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}), # <--- CHANGE THIS
            'fabric_quantity_per_piece': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the form. It makes type-specific fields optional by default
        so that initial validation doesn't fail before the user selects a type.
        """
        super().__init__(*args, **kwargs)
        
        # Define fields specific to each product type
        textile_fields = ['width', 'quality_grade']
        finished_fields = ['selling_price', 'colors', 'size_group', 'fabric_quantity_per_piece']
        
        # Set all type-specific fields to be not required initially
        for field_name in textile_fields + finished_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

        # Populate dropdowns with active choices
        
        if 'category' in self.fields:
            self.fields['category'].queryset = Category.objects.filter(is_active=True)

        # Handle the size_group field safely
        if 'size_groups' in self.fields: # <--- CHANGE THIS
            if PRODUCTION_APP_AVAILABLE:
                self.fields['size_groups'].queryset = SizeGroup.objects.all() # <--- CHANGE THIS
            else:
                self.fields['size_groups'].widget = forms.HiddenInput() # <--- CHANGE THIS
                self.fields['size_groups'].disabled = True # <--- CHANGE THIS

    def clean(self):
        """
        Adds conditional validation and smart code generation based on product type.
        """
        cleaned_data = super().clean()
        product_type = cleaned_data.get('product_type')
        code = cleaned_data.get('code')

        # --- Smart Code Generation on Create ---
        # Only run if creating a new product (self.instance.pk is None) and the code is left blank.
        if not self.instance.pk and not code:
            if product_type:
                # Define prefixes for each product type
                prefix_map = {
                    'fabric': 'FAB',
                    'thread': 'THR',
                    'button': 'BTN',
                    'zipper': 'ZIP',
                    'accessory': 'ACC',
                    'finished': 'FIN',
                }
                prefix = prefix_map.get(product_type, 'PROD')
                
                # Find the highest existing number for this prefix to determine the next one
                last_product = Product.objects.filter(code__startswith=f'{prefix}-').order_by('code').last()
                
                next_num = 1
                if last_product:
                    try:
                        # Extract number from the last code, e.g., 'FAB-0001' -> 1
                        last_num = int(last_product.code.split('-')[-1])
                        next_num = last_num + 1
                    except (ValueError, IndexError):
                        # Fallback if the code format is unexpected
                        next_num = Product.objects.filter(product_type=product_type).count() + 1

                # Loop to ensure the generated code is unique, handling potential race conditions
                while True:
                    new_code = f"{prefix}-{next_num:04d}" # e.g., FAB-0001
                    if not Product.objects.filter(code=new_code).exists():
                        break
                    next_num += 1
                
                cleaned_data['code'] = new_code

        # --- Validation for Textile Products ---
        if product_type == 'fabric':
            if not cleaned_data.get('width'):
                self.add_error('width', 'هذا الحقل مطلوب للأقمشة.')
            if not cleaned_data.get('quality_grade'):
                self.add_error('quality_grade', 'هذا الحقل مطلوب للأقمشة.')

        # --- Validation for Finished Products ---
        elif product_type == 'finished':
            if not cleaned_data.get('selling_price'):
                self.add_error('selling_price', 'سعر البيع مطلوب للمنتجات النهائية.')
        
        return cleaned_data

class StockMovementForm(forms.ModelForm):
    """
    Form for creating a stock movement with a simplified workflow.
    The user can select any product and then any warehouse.
    """
    # This field is for display and user search.
    product_search = forms.CharField(
        label="ابحث عن المنتج (بالاسم أو الكود)",
        required=False, 
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'id': 'id_product_search',
            'placeholder': 'ابدأ الكتابة للبحث عن منتج...'
        })
    )
    
    # The actual product ID is stored in this hidden field.
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=forms.HiddenInput(),
        required=True,
        label=""
    )

    # The warehouse dropdown now lists ALL active warehouses.
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        label="اختر المخزن",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_warehouse'})
    )

    class Meta:
        model = StockMovement
        fields = ['product_search', 'product', 'warehouse', 'movement_type', 'quantity', 'reference_number', 'notes']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم المرجع (فاتورة، إذن صرف، ...)'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'أي تفاصيل إضافية عن الحركة'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing an existing movement, pre-fill the fields.
        if self.instance and self.instance.pk and self.instance.stock_item:
            stock_item = self.instance.stock_item
            self.initial['product_search'] = f"{stock_item.product.name} ({stock_item.product.code})"
            self.initial['product'] = stock_item.product.pk
            self.initial['warehouse'] = stock_item.warehouse.pk

    def clean(self):
        cleaned_data = super().clean()
        movement_type = cleaned_data.get('movement_type')
        quantity = cleaned_data.get('quantity')
        warehouse = cleaned_data.get('warehouse')
        product = cleaned_data.get('product')

        if not (warehouse and product and quantity and movement_type):
            return cleaned_data

        # For 'out' movements, ensure there is enough stock.
        if movement_type == 'out':
            try:
                stock_item = StockItem.objects.get(warehouse=warehouse, product=product)
                if stock_item.available_quantity < quantity:
                    self.add_error('quantity', f'الكمية المطلوبة ({quantity}) أكبر من الكمية المتاحة ({stock_item.available_quantity}).')
            except StockItem.DoesNotExist:
                self.add_error('product', 'لا يمكن عمل حركة "صادر" لمنتج ليس له رصيد في هذا المخزن.')
        
        return cleaned_data

# In your StockTransferForm
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
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            # This validation for same warehouse is already correct
            raise forms.ValidationError('لا يمكن التحويل من نفس المخزن إلى نفسه')

        # --- FIX: Add quantity and stock validation here ---
        if from_warehouse and product and quantity:
            try:
                stock_item = StockItem.objects.get(
                    warehouse=from_warehouse,
                    product=product
                )
                if stock_item.available_quantity < quantity:
                    # This error will now be attached to the form
                    raise forms.ValidationError(
                        f"الكمية المطلوبة ({quantity}) غير متوفرة في المخزن المصدر. الكمية المتاحة: {stock_item.available_quantity}"
                    )
            except StockItem.DoesNotExist:
                # This error will also be attached to the form
                raise forms.ValidationError(f"المنتج '{product.name}' غير موجود في المخزن المصدر.")

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

