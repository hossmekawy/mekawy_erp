from django import forms
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    AssemblyComponent, CutPiece, ProductionOrder, ReceiptConfirmation, SizeGroup, CuttingProcess,
    AssemblyProcess, DyeingProcess, FinishingProcess, ExternalManufacturer,
    ExitPermit, QualityControlCheck, ProductionCostAnalysis, BillOfMaterials, CuttingTable, BOMItem, GarmentDraw, DrawPiece, FinishingComponent , ManufacturerProductPrice  
)
from warehouses.models import Product, StockItem, Warehouse
from django.forms import inlineformset_factory, formset_factory

from django.contrib.auth import get_user_model

# FIX: Add necessary imports for database calculations
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.utils import timezone


User = get_user_model()




class SizeGroupForm(forms.ModelForm):
    sizes_input = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'أدخل المقاسات مفصولة بفاصلة (مثال: XS, S, M, L, XL)',
            'required': True
        }),
        label='المقاسات',
        help_text='أدخل المقاسات مفصولة بفاصلة'
    )
    
    class Meta:
        model = SizeGroup
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم مجموعة المقاسات',
                'required': True
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.sizes:
            self.fields['sizes_input'].initial = ', '.join(self.instance.sizes)
    
    def clean_sizes_input(self):
        sizes_input = self.cleaned_data.get('sizes_input', '')
        if not sizes_input.strip():
            raise forms.ValidationError('يجب إدخال مقاس واحد على الأقل')
        
        # Split and clean sizes
        sizes = [size.strip() for size in sizes_input.split(',') if size.strip()]
        
        if not sizes:
            raise forms.ValidationError('يجب إدخال مقاس واحد على الأقل')
        
        # Remove duplicates while preserving order
        unique_sizes = []
        for size in sizes:
            if size not in unique_sizes:
                unique_sizes.append(size)
        
        return unique_sizes
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.sizes = self.cleaned_data['sizes_input']
        if commit:
            instance.save()
        return instance


# ... (other imports)
from .models import ProductionOrder # and other models

class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = [
            'order_number', 'batch_number', 'product', 'quantity_ordered',
            'priority', 'start_date', 'expected_completion_date', 'notes',
            'textile_stock', 'fabric_meters_allocated'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'textile_stock': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expected_completion_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'order_number': forms.TextInput(attrs={'class': 'form-control'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_ordered': forms.NumberInput(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'fabric_meters_allocated': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True, product_type='finished').order_by('name')
        self.fields['textile_stock'].queryset = StockItem.objects.filter(product__is_active=True, product__product_type='fabric').select_related('product', 'warehouse').order_by('product__name')
        self.fields['textile_stock'].label = "Selected Fabric Stock"
        self.fields['product'].label = "Final Product"

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity_ordered = cleaned_data.get('quantity_ordered')
        textile_stock = cleaned_data.get('textile_stock')

        if product and quantity_ordered:
            fabric_per_piece = Decimal('0.0')
            try:
                # CORRECTED LOGIC: Get fabric quantity from the active BOM
                active_bom = BillOfMaterials.objects.get(product=product, is_active=True)
                fabric_bom_item = active_bom.items.get(material__product_type='fabric')
                fabric_per_piece = fabric_bom_item.quantity

            except BillOfMaterials.DoesNotExist:
                self.add_error('product', f"The product '{product.name}' does not have an active Bill of Materials (BOM).")
                return cleaned_data
            except BOMItem.DoesNotExist:
                self.add_error('product', f"The active BOM for '{product.name}' does not contain a material marked as 'fabric'.")
                return cleaned_data
            except BOMItem.MultipleObjectsReturned:
                self.add_error('product', f"The active BOM for '{product.name}' has multiple fabric materials. Please correct the BOM.")
                return cleaned_data

            # The rest of the calculation now uses the correct value from the BOM
            required_fabric = fabric_per_piece * quantity_ordered
            cleaned_data['fabric_meters_allocated'] = required_fabric.quantize(Decimal('0.01'))

            if textile_stock and textile_stock.available_quantity < required_fabric:
                self.add_error('textile_stock', f'The required fabric quantity ({required_fabric:.2f} meters) is greater than the available quantity in this stock ({textile_stock.available_quantity} meters).')

        return cleaned_data

class CuttingProcessForm(forms.ModelForm):
    class Meta:
        model = CuttingProcess
        fields = [
            'production_order', 'cutting_date', 'cutter', 
            'fabric_waste', 'notes', 'single_layer_pieces',
            'single_layer_fabric_length', 'single_layer_width', 'single_layer_meterage'
        ]
        widgets = {
            'production_order': forms.Select(attrs={'class': 'form-select'}),
            'cutter': forms.Select(attrs={'class': 'form-select'}),
            'cutting_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'fabric_waste': forms.NumberInput(attrs={'class': 'form-control calculated-output', 'readonly': True}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            # New Widgets
            'single_layer_pieces': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 6'}),
            'single_layer_fabric_length': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'مثال: 12.5'}),
            'single_layer_width': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'مثال: 1.5'}),
            'single_layer_meterage': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True}),
        }
    
    def __init__(self, *args, **kwargs):
        # --- FIX: Properly handle the custom queryset passed from the view ---
        # 1. Pop the custom kwarg before calling the parent's init method.
        production_order_queryset = kwargs.pop('production_order_queryset', None)
        
        # 2. Call the parent's __init__ method.
        super().__init__(*args, **kwargs)
        
        # 3. Now, modify the field's queryset.
        self.fields['cutter'].queryset = User.objects.filter(is_active=True)
        if production_order_queryset is not None:
            self.fields['production_order'].queryset = production_order_queryset
        # If it's an update view, add the current instance to the queryset to ensure it's a valid choice
        elif self.instance and self.instance.pk:
             self.fields['production_order'].queryset = ProductionOrder.objects.filter(pk=self.instance.production_order.pk)



# =============================================================================
#  UNCHANGED: CuttingTableForm & FormSet
# =============================================================================
class CuttingTableForm(forms.ModelForm):
    class Meta:
        model = CuttingTable
        fields = ['fabric_length', 'layers_count', 'pieces_per_layer', 'notes']
        widgets = {
            'fabric_length': forms.NumberInput(attrs={'class': 'form-control calculation-input', 'step': '0.01'}),
            'layers_count': forms.NumberInput(attrs={'class': 'form-control calculation-input'}),
            'pieces_per_layer': forms.NumberInput(attrs={'class': 'form-control calculation-input pieces-per-layer-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'})
        }

CuttingTableFormSet = inlineformset_factory(
    CuttingProcess, 
    CuttingTable, 
    form=CuttingTableForm, 
    extra=1, 
    can_delete=True,
    fk_name='cutting_process'
)


class CutPieceForm(forms.ModelForm):
    class Meta:
        model = CutPiece
        fields = ['quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm live-update-quantity'}),
        }

CutPieceFormSet = inlineformset_factory(
    CuttingProcess,
    CutPiece,
    form=CutPieceForm,
    extra=0,
    can_delete=False,
    fk_name='cutting_process'
)

class AssemblyProcessForm(forms.ModelForm):
    class Meta:
        model = AssemblyProcess
        # Exclude 'assembler' - we will set it automatically in the view
        fields = [
            'production_order', 'assembly_type', 'external_manufacturer',
            'quantity_sent', 'quantity_received',
            'defects_count', 'losses_count', 'thread_consumption',
            'thread_cost', 'start_date', 'expected_completion_date',
            'notes', 'defect_notes'
        ]
        # We will render fields manually with widget_tweaks for better UI
        # so widgets dict is not strictly necessary but can be kept for reference
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expected_completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        # Pop custom kwargs before calling super
        available_orders = kwargs.pop('available_orders', None)
        super().__init__(*args, **kwargs)

        # Filter the production_order queryset if provided from the view
        if available_orders is not None:
            self.fields['production_order'].queryset = available_orders

        # Make external_manufacturer not required at the HTML level.
        # We will enforce its requirement in the clean() method.
        self.fields['external_manufacturer'].required = False
        self.fields['external_manufacturer'].queryset = ExternalManufacturer.objects.filter(is_active=True)

        # Provide a helpful message and link if no manufacturers exist
        if not self.fields['external_manufacturer'].queryset.exists():
            add_url = reverse('production:manufacturers:manufacturer_create')
            self.fields['external_manufacturer'].help_text = mark_safe(
                f'لا يوجد مصنعين خارجيين. <a href="{add_url}" target="_blank">أضف مصنعاً جديداً</a>.'
            )
            self.fields['external_manufacturer'].widget.attrs['disabled'] = True
        else:
             self.fields['external_manufacturer'].empty_label = "--- اختر مصنعاً ---"


    def clean(self):
        """
        Add custom validation based on the selected assembly type.
        """
        cleaned_data = super().clean()
        assembly_type = cleaned_data.get('assembly_type')

        if assembly_type == 'outsourced':
            # If outsourced, assembler is not needed, but external_manufacturer is required.
            cleaned_data['assembler'] = None
            if not cleaned_data.get('external_manufacturer'):
                self.add_error('external_manufacturer', 'يجب تحديد المصنع الخارجي لهذا النوع من التجميع.')
        
        elif assembly_type == 'in_house':
            # If in-house, external_manufacturer is not needed. The assembler will be set in the view.
            cleaned_data['external_manufacturer'] = None

        return cleaned_data

class DyeingProcessForm(forms.ModelForm):
    """
    MODIFIED: This form now includes the four new image fields
    for quality control upon return from the dyeing facility.
    """
    class Meta:
        model = DyeingProcess
        fields = [
            'assembly_process', 'dyeing_facility', 'color_specification',
            'quantity_sent', 'quantity_received', 'losses_count',
             'sent_date', 'expected_return_date',
            'notes',
            # NEW: Image fields are now part of the form
        ]

    def __init__(self, *args, **kwargs):
        available_assemblies = kwargs.pop('available_assemblies', None)
        super().__init__(*args, **kwargs)
        if available_assemblies is not None:
            self.fields['assembly_process'].queryset = available_assemblies
        
        # When updating, quantity_sent should not be editable
        if self.instance and self.instance.pk:
            self.fields['quantity_sent'].disabled = True
            self.fields['assembly_process'].disabled = True
            
class FinishingProcessForm(forms.ModelForm):
    """
    MODIFIED: This form now includes the destination_warehouse field,
    which is crucial for the final inventory update.
    """
    class Meta:
        model = FinishingProcess
        fields = [
            'dyeing_process', 
            'destination_warehouse',
            'supervisor',
            'quantity_input', 
            'quantity_output',
            'defects_in_finishing', 
            'start_date', # finishing_cost_per_piece has been removed
            'expected_completion_date', 
            'notes',
            # Checklist fields for the timeline UI
            'ironing_completed', 
            'belt_loops_completed',
            'buttons_completed', 
            'leather_details_completed', 
            'cleaning_completed',
            'pressing_completed', 
            'ticketing_completed', 
            'bagging_completed', 
            'packaging_completed',
        ]

    def __init__(self, *args, **kwargs):
        available_dyeing = kwargs.pop('available_dyeing', None)
        super().__init__(*args, **kwargs)
        if available_dyeing is not None:
            self.fields['dyeing_process'].queryset = available_dyeing

        # When updating, quantity_input should not be editable
        if self.instance and self.instance.pk:
            self.fields['quantity_input'].disabled = True
            self.fields['dyeing_process'].disabled = True

class ExternalManufacturerForm(forms.ModelForm):
    class Meta:
        model = ExternalManufacturer
        fields = [
            'name', 'contact_person', 'phone', 'address',
            'payment_terms_days', 'quality_rating', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'quality_rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ManufacturerProductPriceForm(forms.ModelForm):
    class Meta:
        model = ManufacturerProductPrice
        fields = ['product', 'price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'السعر'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the product dropdown with only finished goods
        self.fields['product'].queryset = Product.objects.filter(is_active=True, product_type='finished').order_by('name')
        self.fields['product'].empty_label = "--- اختر منتج ---"

ManufacturerProductPriceFormSet = inlineformset_factory(
    ExternalManufacturer,
    ManufacturerProductPrice,
    form=ManufacturerProductPriceForm,
    extra=1,
    can_delete=True,
    fk_name='manufacturer' # Explicitly define the foreign key relationship
)


class ExitPermitForm(forms.ModelForm):
    """
    FIXED: The __init__ method has been removed as it was causing a KeyError.
    The form is now simpler and relies on the view to provide initial data.
    """
    class Meta:
        model = ExitPermit
        # The 'production_order' field is intentionally left out, as it will be set
        # automatically in the view based on the context (assembly or dyeing process).
        fields = [
            'production_order','permit_type', 'items_description', 
            'quantity', 'destination', 'purpose', 'valid_until', 'notes'
        ]
        widgets = {
            'production_order': forms.Select(attrs={'class': 'form-select'}),
            'permit_type': forms.Select(attrs={'class': 'form-select'}),
            'items_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'destination': forms.TextInput(attrs={'class': 'form-control'}),
            'purpose': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valid_until': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    def __init__(self, *args, **kwargs):
        # This __init__ is optional but good practice to filter the queryset
        super().__init__(*args, **kwargs)
        # Show only active, non-cancelled orders in the dropdown
        self.fields['production_order'].queryset = ProductionOrder.objects.filter(
            is_active=True
        ).exclude(
            status__in=['completed', 'cancelled']
        )
        self.fields['production_order'].empty_label = "--- اختر أمر إنتاج ---"
class ReceiptConfirmationForm(forms.ModelForm):
    class Meta:
        model = ReceiptConfirmation
        fields = [
            'received_by_name', 'received_by_signature', 'company_representative',
            'quantity_received', 'condition_notes', 'quality_check_passed',
            'photo_evidence', 'additional_documents'
        ]
        widgets = {
            'received_by_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستلم'}),
            'company_representative': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ممثل الشركة (اختياري)'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control'}),
            'condition_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'ملاحظات حول حالة المواد المستلمة'}),
            'quality_check_passed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'photo_evidence': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'additional_documents': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            # The signature field is hidden; its value is set by JavaScript from the canvas.
            'received_by_signature': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        # The view will pass the 'permit' instance to the form
        self.permit = kwargs.pop('permit', None)
        super().__init__(*args, **kwargs)
        if self.permit:
             self.fields['quantity_received'].initial = self.permit.quantity


    def clean_quantity_received(self):
        quantity_received = self.cleaned_data.get('quantity_received')
        if self.permit and quantity_received is not None:
            if quantity_received > self.permit.quantity:
                raise forms.ValidationError(
                    f"الكمية المستلمة ({quantity_received}) لا يمكن أن تكون أكبر من الكمية المرسلة في التصريح ({self.permit.quantity})."
                )
        if quantity_received is not None and quantity_received < 0:
            raise forms.ValidationError("الكمية المستلمة لا يمكن أن تكون سالبة.")
        return quantity_received




class QualityControlCheckForm(forms.ModelForm):
    class Meta:
        model = QualityControlCheck
        # Exclude fields that are set automatically by the view
        fields = [
            'check_type', 'check_date',
            'items_checked', 'items_passed', 'items_failed', 'overall_grade',
            'defect_description', 'corrective_actions', 'notes'
        ]
        widgets = {
            'check_type': forms.Select(attrs={'class': 'form-select'}),
            'check_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'items_checked': forms.NumberInput(attrs={'class': 'form-control'}),
            'items_passed': forms.NumberInput(attrs={'class': 'form-control'}),
            'items_failed': forms.NumberInput(attrs={'class': 'form-control'}),
            'overall_grade': forms.Select(attrs={'class': 'form-select'}),
            'defect_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'corrective_actions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        """
        Custom validation to ensure the number of passed and failed items
        does not exceed the total number of items checked.
        """
        cleaned_data = super().clean()
        items_checked = cleaned_data.get('items_checked')
        items_passed = cleaned_data.get('items_passed')
        items_failed = cleaned_data.get('items_failed')

        if items_checked is not None and items_passed is not None and items_failed is not None:
            if items_passed < 0 or items_failed < 0 or items_checked < 0:
                 raise forms.ValidationError("لا يمكن أن تكون أعداد العناصر سالبة.")
            
            if items_passed + items_failed > items_checked:
                self.add_error('items_passed', "مجموع العناصر المقبولة والمرفوضة لا يمكن أن يكون أكبر من إجمالي العناصر المفحوصة.")
                self.add_error('items_failed', "مجموع العناصر المقبولة والمرفوضة لا يمكن أن يكون أكبر من إجمالي العناصر المفحوصة.")

        return cleaned_data


class ProductionCostAnalysisForm(forms.ModelForm):
    class Meta:
        model = ProductionCostAnalysis
        fields = [
            'production_order', 'fabric_cost', 'thread_cost', 'accessories_cost',
            'cutting_cost', 'assembly_cost', 'dyeing_cost', 'finishing_cost',
            'transportation_cost', 'overhead_cost', 'quality_control_cost',
            'waste_cost', 'defect_cost', 'notes'
        ]

# --- NEW FORM FOR UPDATING ---
class ProductionCostAnalysisUpdateForm(forms.ModelForm):
    """
    A specific form for updating only the manually entered costs
    of a ProductionCostAnalysis instance.
    """
    class Meta:
        model = ProductionCostAnalysis
        fields = [
            'thread_cost', 'accessories_cost', 'cutting_cost',
            'transportation_cost', 'overhead_cost', 'quality_control_cost',
            'waste_cost', 'defect_cost', 'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply form-control class to all fields for consistent styling
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'

class BillOfMaterialsForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ['product', 'size_group', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'size_group': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- CHANGED: Point to the new Product model ---
        self.fields['product'].queryset = Product.objects.filter(is_active=True, product_type='finished').order_by('name')
        self.fields['product'].label = "المنتج النهائي"
        
        # This logic remains good, just ensure it works with the new product model
        self.fields['size_group'].queryset = SizeGroup.objects.all() # Show all size groups
        if 'product' in self.data:
            try:
                product_id = int(self.data.get('product'))
                product = Product.objects.get(id=product_id)
                if product.size_groups.exists():
                    self.fields['size_group'].queryset = product.size_groups.all()
            except (ValueError, TypeError, Product.DoesNotExist):
                pass
        elif self.instance and self.instance.pk and self.instance.product:
            if self.instance.product.size_groups.exists():
                self.fields['size_group'].queryset = self.instance.product.size_groups.all()
    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        size_group = cleaned_data.get('size_group')

        # When creating a new BOM, check if an active one already exists for this combination.
        if not self.instance.pk:
            if product and size_group:
                if BillOfMaterials.objects.filter(product=product, size_group=size_group, is_active=True).exists():
                    raise forms.ValidationError(f'توجد بالفعل قائمة مواد نشطة لهذا المنتج ({product.name}) ومجموعة المقاسات ({size_group.name}). يرجى أرشفة القديمة أولاً.')
        return cleaned_data



class BOMItemForm(forms.ModelForm):
    class Meta:
        model = BOMItem
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select raw-material-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity-input', 'step': '0.01', 'placeholder': 'الكمية'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ملاحظات (اختياري)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- CHANGED: Point to the new Product model ---
        self.fields['material'].queryset = Product.objects.filter(
            is_active=True
        ).exclude(product_type='finished')

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError("الكمية يجب أن تكون أكبر من صفر.")
        return quantity


BOMItemFormSet = inlineformset_factory(
    BillOfMaterials,
    BOMItem,
    form=BOMItemForm,
    extra=1,
    can_delete=True,
    can_delete_extra=True, # Allows deleting the extra empty form
    fk_name='bom'
)

class GarmentDrawForm(forms.ModelForm):
    size = forms.ChoiceField(label="المقاس", widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = GarmentDraw
        fields = ['bom', 'size', 'notes']
        widgets = {
            'bom': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bom'].queryset = BillOfMaterials.objects.filter(is_active=True).select_related('product', 'size_group')
        
        # إذا كان هناك BOM محدد، قم بتعبئة المقاسات المتاحة
        if 'bom' in self.data:
            try:
                bom_id = int(self.data.get('bom'))
                bom = BillOfMaterials.objects.get(id=bom_id)
                self.fields['size'].choices = [(size, size) for size in bom.size_group.sizes]
            except (ValueError, TypeError, BillOfMaterials.DoesNotExist):
                self.fields['size'].choices = []
        elif self.instance and self.instance.pk:
            self.fields['size'].choices = [(size, size) for size in self.instance.bom.size_group.sizes]
            self.fields['size'].initial = self.instance.size


# =============================================================================
#  NEW FORM: DrawPieceForm
# =============================================================================
class DrawPieceForm(forms.ModelForm):
    class Meta:
        model = DrawPiece
        fields = ['name', 'quantity']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: رجل يمين'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 1'}),
        }

# =============================================================================
#  NEW FORMSET: DrawPieceFormSet
# =============================================================================
DrawPieceFormSet = inlineformset_factory(
    GarmentDraw,
    DrawPiece,
    form=DrawPieceForm,
    extra=1,
    can_delete=True,
    fk_name='draw'
)

class AssemblySendForm(forms.ModelForm):
    """
    Form for creating an AssemblyProcess or updating its 'sending' details.
    """
    # FIX: Add start_date to the form fields to allow user input.
    start_date = forms.DateTimeField(
        label="تاريخ ووقت الإرسال",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=True
    )

    class Meta:
        model = AssemblyProcess
        fields = [
            'production_order', 'assembly_type', 'external_manufacturer',
            'quantity_sent', 'start_date', 'expected_completion_date', 'notes',
        ]
        widgets = {
            'assembly_type': forms.RadioSelect,
            # The start_date widget is now defined above for better control.
            'expected_completion_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        available_orders = kwargs.pop('available_orders', None)
        super().__init__(*args, **kwargs)

        if available_orders is not None:
            self.fields['production_order'].queryset = available_orders

        self.fields['external_manufacturer'].required = False
        self.fields['external_manufacturer'].queryset = ExternalManufacturer.objects.filter(is_active=True)
        
        # Set a default value for start_date to now if creating a new instance
        if not self.instance.pk:
            self.fields['start_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')


        if not self.fields['external_manufacturer'].queryset.exists():
            add_url = reverse('production:manufacturers:manufacturer_create')
            self.fields['external_manufacturer'].help_text = mark_safe(
                f'لا يوجد مصنعين. <a href="{add_url}" target="_blank">أضف مصنعاً جديداً</a>.'
            )
            self.fields['external_manufacturer'].widget.attrs['disabled'] = True
        else:
             self.fields['external_manufacturer'].empty_label = "--- اختر مصنعاً ---"

    def clean(self):
        cleaned_data = super().clean()
        assembly_type = cleaned_data.get('assembly_type')

        if assembly_type == 'outsourced' and not cleaned_data.get('external_manufacturer'):
            self.add_error('external_manufacturer', 'يجب تحديد المصنع الخارجي.')
        elif assembly_type == 'in_house':
            cleaned_data['external_manufacturer'] = None

        return cleaned_data


class AssemblyReceiveForm(forms.ModelForm):
    """
    Form used in the modal on the detail page to receive items and complete the process.
    """
    # FIX: Add actual_completion_date to allow user to set the receive date.
    actual_completion_date = forms.DateTimeField(
        label="تاريخ ووقت الاستلام الفعلي",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=True
    )
    
    class Meta:
        model = AssemblyProcess
        fields = [
            'quantity_received', 'defects_count', 'losses_count',
            'thread_consumption', 'thread_cost', 'defect_notes',
            'actual_completion_date' # FIX: Add the field to the list
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the initial value to the current time for convenience
        self.fields['actual_completion_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')


    def clean_quantity_received(self):
        quantity_received = self.cleaned_data.get('quantity_received')
        quantity_sent = self.instance.quantity_sent

        if quantity_received > quantity_sent:
            raise forms.ValidationError(
                f"الكمية المستلمة ({quantity_received}) لا يمكن أن تكون أكبر من الكمية المرسلة ({quantity_sent})."
            )
        return quantity_received

class AssemblyComponentForm(forms.ModelForm):
    class Meta:
        model = AssemblyComponent
        fields = ['material', 'quantity_sent', 'source_warehouse']
        widgets = {
            # We will render the material as a hidden input, its details will be displayed as text.
            'material': forms.HiddenInput(),
            'quantity_sent': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'الكمية', 'min': '0'}),
            'source_warehouse': forms.HiddenInput(),

        }

# This formset will be used to validate and save the components.
BaseAssemblyComponentFormSet = inlineformset_factory(
    AssemblyProcess,
    AssemblyComponent,
    form=AssemblyComponentForm,
    extra=0, # We will add forms dynamically with JS
    can_delete=False,
)

class CustomAssemblyComponentFormSet(BaseAssemblyComponentFormSet):
    """
    FIX: This formset's clean method has been updated to:
    1. Correctly calculate available stock using F() expressions.
    2. Allow sending a quantity of 0 without raising a validation error.
    """
    def clean(self):
        super().clean()
        if any(self.errors):
            # Don't bother validating the formset unless each form is valid on its own
            return

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue

            quantity_to_send = form.cleaned_data.get('quantity_sent')
            material = form.cleaned_data.get('material')
            source_warehouse = form.cleaned_data.get('source_warehouse')

            # Skip validation if key fields are missing
            if not material or quantity_to_send is None:
                continue
            
            # Prevent sending negative quantities
            if quantity_to_send < 0:
                form.add_error('quantity_sent', 'لا يمكن إرسال كمية سالبة.')
                continue

            # If sending 0, no need to check stock.
            if quantity_to_send == 0:
                continue
            if not source_warehouse:
                form.add_error(None, f"الرجاء تحديد مخزن للمادة '{material.name}'.")
                continue
            # Check available stock for the material using a proper DB query
            try:
                stock_item = StockItem.objects.get(product=material, warehouse=source_warehouse)
                available_stock = stock_item.available_quantity
            except StockItem.DoesNotExist:
                available_stock = Decimal('0.0')

            if quantity_to_send > available_stock:
                form.add_error(
                    'quantity_sent',
                    f"الكمية المطلوبة ({quantity_to_send}) أكبر من المتاح في مخزن '{source_warehouse.name}' ({available_stock})."
                )

class DyeingSendForm(forms.ModelForm):
    class Meta:
        model = DyeingProcess
        fields = [
            'assembly_process', 'dyeing_facility', 'color_specification',
            'sent_date', 'expected_return_date',
            'notes'
        ]
        widgets = {
            'sent_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expected_return_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        available_assemblies = kwargs.pop('available_assemblies', None)
        super().__init__(*args, **kwargs)

        if available_assemblies is not None:
            self.fields['assembly_process'].queryset = available_assemblies
        
        self.fields['dyeing_facility'].queryset = ExternalManufacturer.objects.filter(is_active=True)
        self.fields['dyeing_facility'].empty_label = "--- اختر مصنع الصباغة ---"

        if not self.fields['dyeing_facility'].queryset.exists():
            add_url = reverse('production:manufacturers:manufacturer_create')
            self.fields['dyeing_facility'].help_text = mark_safe(
                f'لا يوجد مصنعين. <a href="{add_url}" target="_blank">أضف مصنعاً جديداً</a>.'
            )
            self.fields['dyeing_facility'].widget.attrs['disabled'] = True

class DyeingReceiveForm(forms.ModelForm):
    """
    Form used in the modal on the detail page to receive items from dyeing.
    """
    # FIX: Add actual_return_date to allow user to set the receive date.
    actual_return_date = forms.DateTimeField(
        label="تاريخ ووقت الاستلام الفعلي",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        required=True
    )

    class Meta:
        model = DyeingProcess
        # FIX: Add the new date field to the list of fields.
        fields = ['quantity_received', 'losses_count', 'actual_return_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the initial value to the current time for convenience.
        self.fields['actual_return_date'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')

    def clean_quantity_received(self):
        quantity_received = self.cleaned_data.get('quantity_received')
        quantity_sent = self.instance.quantity_sent

        if quantity_received is not None and quantity_received > quantity_sent:
            raise forms.ValidationError(
                f"الكمية المستلمة ({quantity_received}) لا يمكن أن تكون أكبر من الكمية المرسلة ({quantity_sent})."
            )
        return quantity_received


class FinishingSendForm(forms.ModelForm):
    class Meta:
        model = FinishingProcess
        fields = [
            'dyeing_process',
            'finishing_type', 'external_manufacturer',
            'finisher', 'destination_warehouse', 'supervisor','quantity_input',
            'start_date', 'expected_completion_date', 'notes'
        ]
        widgets = {
            'finishing_type': forms.RadioSelect,
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expected_completion_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        available_dyeing = kwargs.pop('available_dyeing', None)
        super().__init__(*args, **kwargs)

        # MODIFICATION: Renamed the label for the dyeing_process field
        self.fields['dyeing_process'].label = "اختر عملية التشطيب"

        if available_dyeing is not None:
            self.fields['dyeing_process'].queryset = available_dyeing

        # Configure fields for in-house vs outsourced logic
        self.fields['external_manufacturer'].required = False
        self.fields['finisher'].required = False
        self.fields['supervisor'].required = False


        # Filter destination warehouses to only 'finished_product' type
        self.fields['destination_warehouse'].queryset = Warehouse.objects.filter(is_active=True, warehouse_type='finished_goods')

        # Add a check for available destination warehouses
        if not self.fields['destination_warehouse'].queryset.exists():
            add_warehouse_url = reverse('warehouses:warehouse_add')
            self.fields['destination_warehouse'].help_text = mark_safe(
                f'لا توجد مستودعات للمنتجات النهائية. <a href="{add_warehouse_url}" target="_blank">أضف مستودعاً جديداً</a>.'
            )
            self.fields['destination_warehouse'].widget.attrs['disabled'] = True
        else:
            self.fields['destination_warehouse'].empty_label = "--- اختر مخزن نهائي ---"


        self.fields['finisher'].queryset = User.objects.filter(is_active=True)
        self.fields['supervisor'].queryset = User.objects.filter(is_active=True)
        self.fields['external_manufacturer'].queryset = ExternalManufacturer.objects.filter(is_active=True)

        # When updating, dyeing_process and finishing_type should not be editable
        if self.instance and self.instance.pk:
            self.fields['dyeing_process'].disabled = True
            # --- THIS IS THE FIX ---
            # This line disables the field in the form's logic, ensuring its
            # value is respected during validation without being submitted by the browser.
            self.fields['finishing_type'].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        finishing_type = cleaned_data.get('finishing_type')

        if finishing_type == 'outsourced':
            if not cleaned_data.get('external_manufacturer'):
                self.add_error('external_manufacturer', 'يجب تحديد المصنع الخارجي لعملية التشطيب الخارجية.')
            # For outsourced, finisher and supervisor are not applicable
            cleaned_data['finisher'] = None
            cleaned_data['supervisor'] = None
        elif finishing_type == 'in_house':
            # For in-house, external_manufacturer is not applicable
            cleaned_data['external_manufacturer'] = None
            if not cleaned_data.get('finisher'):
                self.add_error('finisher', 'يجب تحديد مسؤول التشطيب الداخلي لعملية التشطيب الداخلية.')
            if not cleaned_data.get('supervisor'):
                self.add_error('supervisor', 'يجب تحديد المشرف لعملية التشطيب الداخلية.')

        return cleaned_data

class FinishingBatchReceiveForm(forms.Form):
    """
    A form to handle receiving a single batch of finished goods.
    """
    receipt_date = forms.DateTimeField(
        label="تاريخ استلام الدفعة",
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        help_text="سيتم استخدام هذا التاريخ في سجل الاستلام."
    )
    quantity_received = forms.IntegerField(
        label="الكمية المستلمة في هذه الدفعة",
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'الكمية الصالحة المستلمة الآن'})
    )
    defects_in_batch = forms.IntegerField(
        label="عدد العيوب في هذه الدفعة",
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    is_final_batch = forms.BooleanField(
        label="هل هذه هي الدفعة الأخيرة؟",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="حدد هذا الخيار لإغلاق العملية نهائياً. سيتم حساب أي فرق متبقي كفاقد."
    )
    notes = forms.CharField(
        label="ملاحظات الدفعة",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'ملاحظات خاصة بهذه الدفعة...'})
    )

    def __init__(self, *args, **kwargs):
        # Store the process instance to use for validation
        self.process_instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        quantity_received = cleaned_data.get('quantity_received', 0)
        defects_in_batch = cleaned_data.get('defects_in_batch', 0)

        if self.process_instance:
            # Calculate how many items are still expected
            total_received_so_far = self.process_instance.quantity_output
            total_defects_so_far = self.process_instance.defects_in_finishing
            quantity_input = self.process_instance.quantity_input
            
            remaining_quantity = quantity_input - (total_received_so_far + total_defects_so_far)

            # Ensure the current batch doesn't exceed the remaining quantity
            if (quantity_received + defects_in_batch) > remaining_quantity:
                raise forms.ValidationError(
                    f"إجمالي المدخلات لهذه الدفعة ({quantity_received + defects_in_batch}) "
                    f"أكبر من الكمية المتبقية المتوقعة ({remaining_quantity})."
                )
        return cleaned_data


class FinishingComponentForm(forms.ModelForm):
    class Meta:
        model = FinishingComponent
        fields = ['material', 'quantity_sent', 'source_warehouse']
        widgets = {
            'material': forms.HiddenInput(), # Material will be displayed as text
            'quantity_sent': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'الكمية', 'min': '0'}),
            'source_warehouse': forms.HiddenInput(), # Warehouse will be a dynamic select
        }

# Base formset for FinishingComponent
BaseFinishingComponentFormSet = inlineformset_factory(
    FinishingProcess,
    FinishingComponent,
    form=FinishingComponentForm,
    extra=0, # We will add forms dynamically with JS
    can_delete=False,
)

class CustomFinishingComponentFormSet(BaseFinishingComponentFormSet):
    """
    Custom formset for FinishingComponent to add validation for stock availability.
    """
    def clean(self):
        super().clean()
        if any(self.errors):
            # Don't bother validating the formset unless each form is valid on its own
            return

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue

            quantity_to_send = form.cleaned_data.get('quantity_sent')
            material = form.cleaned_data.get('material')
            source_warehouse = form.cleaned_data.get('source_warehouse')

            # Skip validation if key fields are missing
            if not material or quantity_to_send is None:
                continue
            
            # Prevent sending negative quantities
            if quantity_to_send < 0:
                form.add_error('quantity_sent', 'لا يمكن إرسال كمية سالبة.')
                continue

            # If sending 0, no need to check stock.
            if quantity_to_send == 0:
                continue
            if not source_warehouse:
                form.add_error(None, f"الرجاء تحديد مخزن للمادة '{material.name}'.")
                continue
            
            # Check available stock for the material using a proper DB query
            try:
                stock_item = StockItem.objects.get(product=material, warehouse=source_warehouse)
                available_stock = stock_item.available_quantity
            except StockItem.DoesNotExist:
                available_stock = Decimal('0.0')

            if quantity_to_send > available_stock:
                form.add_error(
                    'quantity_sent',
                    f"الكمية المطلوبة ({quantity_to_send}) أكبر من المتاح في مخزن '{source_warehouse.name}' ({available_stock})."
                )



class SendAdditionalComponentForm(forms.Form):
    """
    A single form for one material being sent to a manufacturer.
    This will be used within a formset.
    """
    # --- FIX: The queryset is now Product.objects.all() to accept any valid product ID.
    # The __init__ method has been removed as it was causing the validation error.
    material = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=forms.HiddenInput()
    )
    quantity_to_send = forms.DecimalField(
        min_value=Decimal('0.00'),
        required=False, # We'll only process forms where quantity > 0
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'الكمية', 'step': '0.01'})
    )
    # --- FIX: The queryset now includes both 'components' and 'textile' warehouses
    # to match what the user sees in the dropdown.
    source_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(warehouse_type__in=['components', 'textile'], is_active=True),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label="المخزن المصدر"
    )


# We use a base formset factory, not an inline one, because we are creating
# multiple objects (AssemblyComponent, StockMovement, ExitPermit) from this formset.
SendAdditionalComponentFormSet = formset_factory(SendAdditionalComponentForm, extra=0)
