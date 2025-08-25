from django import forms
from .models import Customer, Interaction
from phonenumber_field.formfields import PhoneNumberField

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'name', 'customer_type', 'phone_number', 'email', 
            'address_line_1', 'address_line_2', 'city', 'governorate', 'country',
            'company_name', 'tax_id', 'notes', 'is_active'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-control'})

# --- ADD THIS NEW FORM ---
class CustomerPOSForm(forms.ModelForm):
    """
    A simplified form specifically for creating a customer from the POS modal.
    """
    class Meta:
        model = Customer
        fields = ['name', 'phone_number', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False


class InteractionForm(forms.ModelForm):
    class Meta:
        model = Interaction
        fields = ['interaction_type', 'summary']
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 4, 'placeholder': 'اكتب ملخصًا للتفاعل هنا...'}),
            'interaction_type': forms.Select(attrs={'class': 'form-select'})
        }
