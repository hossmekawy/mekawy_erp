# finance/forms.py

from django import forms
from .models import Account, Transaction ,  CashCount, CustodyHandover
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()


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

    def __init__(self, *args, **kwargs):
        """
        Override the init method to set a default 'from' account.
        """
        super().__init__(*args, **kwargs)
        try:
            # Attempt to find the account named 'خزينه المكتب'
            default_account = Account.objects.get(name='خزينه المكتب')
            # Set it as the initial value for the 'account' field
            self.fields['account'].initial = default_account.pk
        except Account.DoesNotExist:
            # If the account doesn't exist, do nothing. The form will fall back to
            # the default behavior (usually the first account or an empty selection).
            pass

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
        
        # --- FIX: Set initial value if only one asset account exists ---
        asset_accounts = self.fields['payment_account'].queryset
        if asset_accounts.count() == 1:
            self.fields['payment_account'].initial = asset_accounts.first()


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

class CashCountForm(forms.ModelForm):
    """
    Form for a user to perform a cash count on a treasury/asset account.
    """
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(account_type='ASSET'),
        label="اختر الخزينة",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = CashCount
        fields = ['account', 'counted_amount', 'notes']
        widgets = {
            'counted_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'أدخل المبلغ الذي قمت بجردِه'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'أي ملاحظات حول عملية الجرد...'}),
        }


class CustodyHandoverForm(forms.ModelForm):
    """
    Form for creating a custody handover record.
    """
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(account_type='ASSET'),
        label="العهدة (الحساب)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    to_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        label="الموظف المُستلِم",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = CustodyHandover
        fields = ['account', 'amount_handed_over', 'to_user', 'notes']
        widgets = {
            'amount_handed_over': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'المبلغ الموجود بالعهدة وقت التسليم'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'أي ملاحظات أو تفاصيل حول التسليم...'}),
        }

    def __init__(self, *args, **kwargs):
        # Exclude the current user from the list of users to whom custody can be handed over.
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['to_user'].queryset = User.objects.filter(is_active=True).exclude(pk=self.user.pk)

    def clean_to_user(self):
        to_user = self.cleaned_data.get('to_user')
        if self.user and to_user == self.user:
            raise ValidationError("لا يمكن تسليم العهدة لنفسك.")
        return to_user
