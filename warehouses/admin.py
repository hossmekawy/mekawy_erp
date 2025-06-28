from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Category, Warehouse, Product, StockItem, StockMovement, StockTransfer

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'is_active', 'product_count']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    
    def product_count(self, obj):
        count = obj.product_set.count()
        if count > 0:
            url = reverse('admin:warehouses_product_changelist') + f'?category__id__exact={obj.id}'
            return format_html('<a href="{}">{} منتج</a>', url, count)
        return '0 منتج'
    product_count.short_description = 'عدد المنتجات'

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'manager', 'is_active', 'stock_items_count', 'created_at']
    list_filter = ['is_active', 'created_at', 'manager']
    search_fields = ['name', 'code', 'description']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'code', 'description')
        }),
        ('الإدارة', {
            'fields': ('manager', 'is_active')
        }),
        ('التواريخ', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def stock_items_count(self, obj):
        count = obj.stock_items.count()
        if count > 0:
            url = reverse('admin:warehouses_stockitem_changelist') + f'?warehouse__id__exact={obj.id}'
            return format_html('<a href="{}">{} عنصر</a>', url, count)
        return '0 عنصر'
    stock_items_count.short_description = 'عناصر المخزون'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'product_type', 'unit', 'cost_price', 'selling_price', 'total_stock_display', 'is_active']
    list_filter = ['category', 'product_type', 'unit', 'is_active', 'created_at']
    search_fields = ['name', 'code', 'barcode']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'total_stock_display']
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'code', 'barcode', 'category', 'product_type')
        }),
        ('التسعير والوحدة', {
            'fields': ('unit', 'cost_price', 'selling_price', 'min_stock_level')
        }),
        ('الحالة والإحصائيات', {
            'fields': ('is_active', 'total_stock_display', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_stock_display(self, obj):
        total = obj.total_stock
        if total <= obj.min_stock_level:
            return format_html('<span style="color: red; font-weight: bold;">{}</span>', total)
        return total
    total_stock_display.short_description = 'إجمالي المخزون'

class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    readonly_fields = ['created_at', 'created_by']
    fields = ['movement_type', 'quantity', 'reference_number', 'notes', 'created_by', 'created_at']

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity', 'reserved_quantity', 'available_quantity_display', 'is_low_stock_display', 'last_updated']
    list_filter = ['warehouse', 'product__category', 'last_updated']
    search_fields = ['product__name', 'product__code', 'warehouse__name']
    readonly_fields = ['last_updated', 'available_quantity_display', 'is_low_stock_display']
    inlines = [StockMovementInline]
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('warehouse', 'product', 'location')
        }),
        ('الكميات', {
            'fields': ('quantity', 'reserved_quantity', 'available_quantity_display')
        }),
        ('الحالة', {
            'fields': ('is_low_stock_display', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def available_quantity_display(self, obj):
        available = obj.available_quantity
        if available <= 0:
            return format_html('<span style="color: red; font-weight: bold;">{}</span>', available)
        return available
    available_quantity_display.short_description = 'الكمية المتاحة'
    
    def is_low_stock_display(self, obj):
        if obj.is_low_stock:
            return format_html('<span style="color: red;">⚠️ منخفض</span>')
        return format_html('<span style="color: green;">✅ جيد</span>')
    is_low_stock_display.short_description = 'حالة المخزون'

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['stock_item', 'movement_type', 'quantity', 'reference_number', 'created_by', 'created_at']
    list_filter = ['movement_type', 'created_at', 'stock_item__warehouse', 'created_by']
    search_fields = ['stock_item__product__name', 'reference_number', 'notes']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('معلومات الحركة', {
            'fields': ('stock_item', 'movement_type', 'quantity')
        }),
        ('التفاصيل', {
            'fields': ('reference_number', 'notes')
        }),
        ('معلومات النظام', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'product', 'from_warehouse', 'to_warehouse', 'quantity', 'status', 'requested_by', 'requested_at']
    list_filter = ['status', 'requested_at', 'from_warehouse', 'to_warehouse']
    search_fields = ['transfer_number', 'product__name', 'reason']
    readonly_fields = ['transfer_number', 'requested_at', 'approved_at', 'completed_at']
    date_hierarchy = 'requested_at'
    
    fieldsets = (
        ('معلومات التحويل', {
            'fields': ('transfer_number', 'from_warehouse', 'to_warehouse', 'product', 'quantity')
        }),
        ('التفاصيل', {
            'fields': ('reason', 'notes', 'status')
        }),
        ('المعتمدون', {
            'fields': ('requested_by', 'approved_by', 'completed_by'),
            'classes': ('collapse',)
        }),
        ('التواريخ', {
            'fields': ('requested_at', 'approved_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # إذا كان إنشاء جديد
            obj.requested_by = request.user
            # إنشاء رقم تحويل تلقائي
            if not obj.transfer_number:
                import datetime
                today = datetime.date.today()
                count = StockTransfer.objects.filter(requested_at__date=today).count() + 1
                obj.transfer_number = f"TR-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save_model(request, obj, form, change)

# تخصيص عنوان الإدارة
admin.site.site_header = "إدارة نظام المخازن - Mekawy ERP"
admin.site.site_title = "إدارة المخازن"
admin.site.index_title = "لوحة تحكم المخازن"
