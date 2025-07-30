# finance/forms.py

from django import forms
from .models import Account, Transaction
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from decimal import Decimal

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: الخزينة الرئيسية'}),
        }


class TransactionForm(forms.ModelForm):
    # We make `to_account` not required at the form level and handle it in clean()
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
        """
        Custom validation for transactions.
        """
        cleaned_data = super().clean()
        trans_type = cleaned_data.get('type')
        amount = cleaned_data.get('amount', Decimal('0'))
        from_account = cleaned_data.get('account')
        to_account = cleaned_data.get('to_account')

        if amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر.")

        if trans_type in ['WITHDRAWAL', 'TRANSFER']:
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
        """
        Process the transaction and update account balances atomically.
        """
        # Create transaction instance but don't save to DB yet
        instance = super().save(commit=False)
        
        from_account = self.cleaned_data.get('account')
        to_account = self.cleaned_data.get('to_account')
        amount = self.cleaned_data.get('amount')
        
        if instance.type == 'DEPOSIT':
            from_account.balance += amount
        
        elif instance.type == 'WITHDRAWAL':
            from_account.balance -= amount
            
        elif instance.type == 'TRANSFER':
            from_account.balance -= amount
            to_account.balance += amount
            if commit:
                to_account.save()
        
        if commit:
            from_account.save()
            instance.save()
            
        return instance