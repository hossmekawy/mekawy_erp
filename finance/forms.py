# finance/forms.py

from django import forms
from django.contrib.contenttypes.models import ContentType
from .models import Account, AccountCategory, Invoice, Payment, Expense

class AccountForm(forms.ModelForm):
    """
    Form for creating and updating Account instances.
    """
    class Meta:
        model = Account
        fields = ['name', 'code', 'category', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InvoiceForm(forms.ModelForm):
    """
    Form for creating and updating Invoices.
    The 'recipient' fields are handled in the view since it's a GenericForeignKey.
    """
    class Meta:
        model = Invoice
        fields = [
            'invoice_number', 'issue_date', 'due_date', 
            'total_amount', 'status',  'notes'
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            # 'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class PaymentForm(forms.ModelForm):
    """
    Form for recording a Payment against an Invoice.
    """
    class Meta:
        model = Payment
        fields = ['payment_date', 'amount', 'payment_method', 'reference', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        # The view will pass the invoice instance to the form
        self.invoice = kwargs.pop('invoice', None)
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if self.invoice and amount > self.invoice.balance_due:
            raise forms.ValidationError(f"مبلغ الدفعة لا يمكن أن يكون أكبر من الرصيد المستحق ({self.invoice.balance_due}).")
        return amount

class ExpenseForm(forms.ModelForm):
    """
    Form for recording a general Expense.
    """
    class Meta:
        model = Expense
        fields = [
            'expense_account', 'source_account', 'description', 'amount', 
            'expense_date'
        ]
        widgets = {
            'expense_account': forms.Select(attrs={'class': 'form-select'}),
            'source_account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            # 'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Querysets are already limited in the model definition, but this is good practice
        self.fields['expense_account'].queryset = Account.objects.filter(category__category_type='expense', is_active=True)
        self.fields['source_account'].queryset = Account.objects.filter(category__category_type='asset', is_active=True)


