from django.contrib import admin
from .models import Customer, Interaction

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_name', 'customer_type', 'phone_number', 'email', 'is_active', 'created_at')
    list_filter = ('customer_type', 'is_active', 'governorate', 'created_at')
    search_fields = ('name', 'company_name', 'phone_number', 'email', 'tax_id')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('name', 'customer_type', 'phone_number', 'email', 'is_active')
        }),
        ('معلومات الشركة', {
            'classes': ('collapse',),
            'fields': ('company_name', 'tax_id'),
        }),
        ('العنوان', {
            'classes': ('collapse',),
            'fields': ('address_line_1', 'address_line_2', 'city', 'governorate', 'country'),
        }),
        ('معلومات إضافية', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
        }),
    )

@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'interaction_type', 'interaction_date', 'user', 'summary')
    list_filter = ('interaction_type', 'interaction_date', 'user')
    search_fields = ('customer__name', 'summary')
    autocomplete_fields = ['customer']
