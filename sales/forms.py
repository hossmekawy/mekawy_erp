from django import forms
from django.forms import inlineformset_factory
from .models import SalesInvoice, InvoiceItem, PriceList, PriceListItem

class SalesInvoiceForm(forms.ModelForm):
    """
    Form for creating and updating Sales Invoices in the back-office.
    """
    class Meta:
        model = SalesInvoice
        fields = [
            'customer', 
            'warehouse', 
            'issue_date', 
            'due_date', 
            'status', 
            'notes', 
            'discount_amount', 
            'tax_amount'
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-control select2'}),
            'warehouse': forms.Select(attrs={'class': 'form-control select2'}),
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'discount_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'customer': 'العميل',
            'warehouse': 'المخزن',
            'issue_date': 'تاريخ الإصدار',
            'due_date': 'تاريخ الاستحقاق',
            'status': 'الحالة',
            'notes': 'ملاحظات',
            'discount_amount': 'مبلغ الخصم',
            'tax_amount': 'مبلغ الضريبة',
        }

class InvoiceItemForm(forms.ModelForm):
    """
    Form for a single item within a sales invoice.
    """
    class Meta:
        model = InvoiceItem
        fields = ['product', 'quantity', 'unit_price', 'discount_percentage']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity-input'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control price-input'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-control discount-input'}),
        }

# Formset for handling multiple invoice items within a single invoice form
InvoiceItemFormSet = inlineformset_factory(
    SalesInvoice, 
    InvoiceItem, 
    form=InvoiceItemForm,
    extra=1, 
    can_delete=True,
    can_delete_extra=True
)

class PriceListForm(forms.ModelForm):
    """
    Form for creating and updating Price Lists.
    """
    class Meta:
        model = PriceList
        fields = ['name', 'is_active', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
        labels = {
            'name': 'اسم قائمة الأسعار',
            'is_active': 'نشطة',
            'start_date': 'تاريخ البدء',
            'end_date': 'تاريخ الانتهاء',
        }

class PriceListItemForm(forms.ModelForm):
    """
    Form for a single item within a price list.
    """
    class Meta:
        model = PriceListItem
        fields = ['product', 'price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

