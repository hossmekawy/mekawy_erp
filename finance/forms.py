# finance/forms.py

from django import forms
from .models import Account, Transaction
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from decimal import Decimal

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
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
        """
        Performs a 'soft' validation without database locking for quick user feedback.
        The real, secure check happens in the save() method.
        """
        cleaned_data = super().clean()
        trans_type = cleaned_data.get('type')
        amount = cleaned_data.get('amount')
        from_account = cleaned_data.get('account')
        to_account = cleaned_data.get('to_account')

        if not amount or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر.")

        if from_account and amount and trans_type in ['WITHDRAWAL', 'TRANSFER']:
            if from_account.balance < amount:
                # This is a non-locking, preliminary check for better UX.
                raise ValidationError(f"الرصيد الحالي في '{from_account.name}' ({from_account.balance}) قد يكون غير كافٍ.")

        if trans_type == 'TRANSFER':
            if not to_account:
                raise ValidationError("يجب تحديد الحساب المراد التحويل إليه.")
            if from_account == to_account:
                raise ValidationError("لا يمكن التحويل إلى نفس الحساب.")
        
        return cleaned_data

    def save(self, commit=True):
        """
        Handles the entire process atomically: locking, final validation, and saving.
        This is the single source of truth for creating a transaction and updating balances.
        """
        instance = super().save(commit=False)
        
        # We wrap the entire logic in a single atomic transaction.
        try:
            with db_transaction.atomic():
                # Use select_for_update to lock the rows and get the definitive current state.
                from_account = Account.objects.select_for_update().get(pk=instance.account.pk)
                to_account = None
                if instance.type == 'TRANSFER':
                    if not instance.to_account:
                        raise ValidationError("يجب تحديد الحساب المراد التحويل إليه.")
                    to_account = Account.objects.select_for_update().get(pk=instance.to_account.pk)

                # Perform the definitive, locked balance check.
                if instance.type in ['WITHDRAWAL', 'TRANSFER']:
                    if from_account.balance < instance.amount:
                        # This error will be correctly displayed on the form to the user.
                        raise ValidationError(f"الرصيد الفعلي في '{from_account.name}' غير كافٍ لإتمام العملية.")

                # Update balances based on transaction type
                if instance.type == 'DEPOSIT':
                    from_account.balance += instance.amount
                elif instance.type == 'WITHDRAWAL':
                    from_account.balance -= instance.amount
                elif instance.type == 'TRANSFER':
                    from_account.balance -= instance.amount
                    to_account.balance += instance.amount
                
                # Save the updated accounts
                from_account.save()
                if to_account:
                    to_account.save()
                
                # Save the transaction instance itself
                if commit:
                    instance.save()

        except Account.DoesNotExist:
            raise ValidationError("أحد الحسابات لم يعد موجوداً. يرجى تحديث الصفحة والمحاولة مرة أخرى.")
            
        return instance


class ManufacturerPaymentForm(forms.Form):
    amount = forms.DecimalField(
        label="مبلغ الدفعة",
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'})
    )
    payment_account = forms.ModelChoiceField(
        label="الدفع من حساب",
        queryset=Account.objects.filter(account_type='ASSET'),
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
        if not self.manufacturer_account:
            raise ValueError("Critical: Manufacturer does not have a linked finance account.")

    def clean(self):
        """
        Performs a 'soft' validation without locking for quick user feedback.
        """
        cleaned_data = super().clean()
        payment_account = cleaned_data.get('payment_account')
        amount = cleaned_data.get('amount')

        if payment_account and amount:
            if payment_account.balance < amount:
                raise ValidationError(f"الرصيد الحالي في '{payment_account.name}' ({payment_account.balance}) قد يكون غير كافٍ.")
        
        return cleaned_data

    def save(self):
        """
        Handles the manufacturer payment atomically.
        """
        payment_account_data = self.cleaned_data['payment_account']
        manufacturer_account_data = self.manufacturer.finance_account
        amount = self.cleaned_data['amount']

        try:
            with db_transaction.atomic():
                # 1. Lock the rows to prevent race conditions
                payment_account = Account.objects.select_for_update().get(pk=payment_account_data.pk)
                manufacturer_account = Account.objects.select_for_update().get(pk=manufacturer_account_data.pk)

                # 2. Perform the definitive balance check inside the lock
                if payment_account.balance < amount:
                    raise ValidationError(f"الرصيد الفعلي في '{payment_account.name}' غير كافٍ.")

                # 3. Update balances
                payment_account.balance -= amount  # Decrease asset
                manufacturer_account.balance -= amount  # Decrease liability (what you owe)

                # 4. Save the updated accounts
                payment_account.save()
                manufacturer_account.save()

                # 5. Create the transaction record
                transaction = Transaction.objects.create(
                    account=payment_account,
                    to_account=manufacturer_account,
                    type='MANUFACTURER_PAYMENT',
                    amount=amount,
                    description=self.cleaned_data.get('description') or f"دفعة إلى المصنع: {self.manufacturer.name}",
                    reference=self.cleaned_data.get('reference')
                )
        except Account.DoesNotExist:
            raise ValidationError("أحد الحسابات لم يعد موجوداً. يرجى تحديث الصفحة والمحاولة مرة أخرى.")

        return transaction
