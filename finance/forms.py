# finance/forms.py

from django import forms
from .models import Account, Transaction
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from decimal import Decimal

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        # --- FIX: Allow editing account type ---
        fields = ['name', 'account_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: الخزينة الرئيسية'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
        }


class TransactionForm(forms.ModelForm):
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        required=False,
        label="إلى حساب",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Transaction
        fields = ['type', 'account', 'to_account', 'amount', 'description', 'reference']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'account': forms.Select(attrs={'class': 'form-select', 'id': 'from_account_select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'account': 'من حساب'
        }

    def clean(self):
        cleaned_data = super().clean()
        trans_type = cleaned_data.get('type')
        amount = cleaned_data.get('amount', Decimal('0'))
        from_account = cleaned_data.get('account')
        to_account = cleaned_data.get('to_account')

        if not amount or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر.")

        if trans_type in ['WITHDRAWAL', 'TRANSFER', 'MANUFACTURER_PAYMENT']:
            if not from_account:
                raise ValidationError("يجب تحديد الحساب للسحب أو التحويل.")
            if from_account.balance < amount:
                raise ValidationError(f"الرصيد في '{from_account.name}' غير كافٍ. الرصيد الحالي: {from_account.balance}")

        if trans_type == 'TRANSFER':
            if not to_account:
                raise ValidationError("يجب تحديد الحساب المراد التحويل إليه.")
            if from_account == to_account:
                raise ValidationError("لا يمكن التحويل إلى نفس الحساب.")
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        from_account = self.cleaned_data.get('account')
        to_account = self.cleaned_data.get('to_account')
        amount = self.cleaned_data.get('amount')
        
        # This logic needs to be updated for the new types
        with db_transaction.atomic():
            if instance.type == 'DEPOSIT':
                acc = instance.account
                acc.balance += amount
                acc.save()
            
            elif instance.type == 'WITHDRAWAL':
                acc = instance.account
                acc.balance -= amount
                acc.save()
                
            elif instance.type == 'TRANSFER':
                from_acc = instance.account
                to_acc = instance.to_account
                from_acc.balance -= amount
                to_acc.balance += amount
                from_acc.save()
                to_acc.save()
            
            # The MANUFACTURING_DEBT is handled by the signal, not forms.
            # The ManufacturerPaymentForm will handle its own logic.
            
            if commit:
                instance.save()
            
        return instance

# --- NEW: Form for making payments to manufacturers ---
class ManufacturerPaymentForm(forms.Form):
    """
    Form to simplify making a payment to a manufacturer.
    This creates a 'MANUFACTURER_PAYMENT' transaction.
    """
    amount = forms.DecimalField(
        label="مبلغ الدفعة",
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'})
    )
    payment_account = forms.ModelChoiceField(
        label="الدفع من حساب",
        queryset=Account.objects.filter(account_type='ASSET'), # Pay from Treasury/Bank
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    description = forms.CharField(
        label="الوصف / ملاحظات",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    reference = forms.CharField(label="مرجع", required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        self.manufacturer = kwargs.pop('manufacturer')
        super().__init__(*args, **kwargs)
        self.manufacturer_account = self.manufacturer.finance_account

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        payment_account = self.cleaned_data.get('payment_account')
        if payment_account and amount > payment_account.balance:
            raise ValidationError(f"الرصيد في '{payment_account.name}' غير كافٍ. الرصيد الحالي: {payment_account.balance}")
        return amount

    def save(self):
        amount = self.cleaned_data['amount']
        payment_account = self.cleaned_data['payment_account']
        
        with db_transaction.atomic():
            # 1. Decrease the balance of the payment account (e.g., Treasury)
            payment_account.balance -= amount
            payment_account.save()

            # 2. Decrease the balance of the manufacturer's liability account
            self.manufacturer_account.balance -= amount
            self.manufacturer_account.save()

            # 3. Create the transaction record
            transaction = Transaction.objects.create(
                account=self.manufacturer_account,
                type='MANUFACTURER_PAYMENT',
                amount=amount,
                description=self.cleaned_data.get('description') or f"دفعة إلى المصنع: {self.manufacturer.name}",
                reference=self.cleaned_data.get('reference')
            )
        return transaction
