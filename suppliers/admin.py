from django.contrib import admin
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, Payment,
    SupplierRating, SupplierContact, SupplierDocument,
    PurchaseOrderDelivery, PurchaseOrderDeliveryItem,
    SupplierPerformanceMetric
)

class SupplierContactInline(admin.TabularInline):
    model = SupplierContact
    extra = 1
    fields = ['name', 'position', 'phone', 'email', 'is_primary', 'notes']

class SupplierDocumentInline(admin.TabularInline):
    model = SupplierDocument
    extra = 0
    fields = ['document_type', 'title', 'file', 'expiry_date', 'notes']
    readonly_fields = ['uploaded_by', 'uploaded_at']

class SupplierRatingInline(admin.TabularInline):
    model = SupplierRating
    extra = 0
    readonly_fields = ['overall_rating', 'rating_date', 'rated_by']
    fields = [
        'purchase_order', 'quality_rating', 'delivery_rating',
        'price_rating', 'service_rating', 'communication_rating',
        'overall_rating', 'rated_by', 'rating_date'
    ]

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'supplier_type', 'contact_person',
        'phone', 'current_rating', 'get_rating_count', 'is_active'
    ]
    list_filter = ['supplier_type', 'is_active', 'created_at']
    search_fields = ['name', 'code', 'contact_person']
    readonly_fields = ['current_rating', 'created_at', 'updated_at']
    inlines = [SupplierContactInline, SupplierDocumentInline, SupplierRatingInline]

    def get_rating_count(self, obj):
        return obj.ratings.count()
    get_rating_count.short_description = 'عدد التقييمات'

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'status', 'total_amount', 'expected_delivery_date', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['po_number', 'supplier__name']
    readonly_fields = ['po_number', 'subtotal', 'total_amount', 'created_at', 'updated_at']
    inlines = [PurchaseOrderItemInline]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'supplier', 'payment_type', 'amount', 'status', 'payment_date']
    list_filter = ['payment_type', 'payment_method', 'status']
    search_fields = ['payment_number', 'supplier__name']
    readonly_fields = ['payment_number', 'created_at']

@admin.register(SupplierRating)
class SupplierRatingAdmin(admin.ModelAdmin):
    list_display = [
        'supplier', 'overall_rating', 'purchase_order', 
        'rated_by', 'rating_date', 'get_rating_text'
    ]
    list_filter = [
        'overall_rating', 'rating_date', 'supplier__supplier_type',
        'quality_rating', 'delivery_rating', 'price_rating'
    ]
    search_fields = ['supplier__name', 'comments', 'rated_by__username']
    readonly_fields = ['overall_rating', 'rating_date']
    date_hierarchy = 'rating_date'
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('supplier', 'purchase_order', 'rated_by', 'rating_date')
        }),
        ('التقييمات', {
            'fields': (
                'quality_rating', 'delivery_rating', 'price_rating',
                'service_rating', 'communication_rating', 'overall_rating'
            )
        }),
        ('تفاصيل إضافية', {
            'fields': ('comments', 'season'),
            'classes': ('collapse',)
        })
    )
    
    def get_rating_text(self, obj):
        return obj.get_rating_text()
    get_rating_text.short_description = 'تقييم نصي'
    get_rating_text.admin_order_field = 'overall_rating'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'supplier', 'purchase_order', 'rated_by'
        )

@admin.register(SupplierPerformanceMetric)
class SupplierPerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ['supplier', 'period_start', 'period_end', 'completion_rate', 'on_time_delivery_rate', 'average_rating']
    list_filter = ['period_start', 'period_end']
    search_fields = ['supplier__name']
    readonly_fields = ['completion_rate', 'on_time_delivery_rate', 'average_rating', 'calculated_at']

@admin.register(SupplierContact)
class SupplierContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'supplier', 'position', 'phone', 'is_primary']
    list_filter = ['is_primary', 'supplier']
    search_fields = ['name', 'supplier__name', 'phone']

@admin.register(SupplierDocument)
class SupplierDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'supplier', 'document_type', 'expiry_date', 'is_expired', 'uploaded_at']
    list_filter = ['document_type', 'expiry_date', 'uploaded_at']
    search_fields = ['title', 'supplier__name']
    readonly_fields = ['is_expired', 'days_to_expiry', 'uploaded_at']

class PurchaseOrderDeliveryItemInline(admin.TabularInline):
    model = PurchaseOrderDeliveryItem
    extra = 1

@admin.register(PurchaseOrderDelivery)
class PurchaseOrderDeliveryAdmin(admin.ModelAdmin):
    list_display = ['delivery_number', 'purchase_order', 'delivery_date', 'received_by', 'is_complete']
    list_filter = ['delivery_date', 'is_complete', 'quality_check_passed']
    search_fields = ['delivery_number', 'purchase_order__po_number']
    readonly_fields = ['delivery_number', 'created_at']
    inlines = [PurchaseOrderDeliveryItemInline]
