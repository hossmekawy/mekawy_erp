from django import forms
from .models import SalesInvoice, InvoiceItem, PriceList, PriceListItem

class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = ['name', 'is_active', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

class PriceListItemForm(forms.ModelForm):
    class Meta:
        model = PriceListItem
        fields = ['product', 'price']


class SalesInvoiceForm(forms.ModelForm):
    class Meta:
        model = SalesInvoice
        # FIX: Removed 'invoice_number' as it is non-editable
        fields = ['customer', 'issue_date', 'due_date', 'status', 'payment_terms', 'warehouse', 'notes', 'discount_amount', 'tax_amount']
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['product', 'quantity', 'unit_price', 'discount_percentage']

InvoiceItemFormSet = forms.inlineformset_factory(
    SalesInvoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,
    can_delete=True,
    can_delete_extra=True
)
