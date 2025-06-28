from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum, Avg
from .models import (
    TextileStock, FinishedProduct, ProductionOrder, CuttingProcess, CuttingTable,
    CutPiece, ExternalManufacturer, AssemblyProcess, AssembledGarment,
    DyeingProcess, DyedGarment, BillOfMaterials, FinishingProcess, FinalProduct,
    ProcessDocument, ExitPermit, ReceiptConfirmation, ProductionCostAnalysis,
    QualityControlCheck, ProductionReport,ProductCategory,SizeGroup,BOMItem
)

@admin.register(TextileStock)
class TextileStockAdmin(admin.ModelAdmin):
    list_display = ['name', 'fabric_type', 'color', 'width', 'length_available', 'cost_per_meter', 'warehouse', 'quality_grade', 'is_active']
    list_filter = ['fabric_type', 'warehouse', 'quality_grade', 'is_active', 'supplier']
    search_fields = ['name', 'color', 'batch_number', 'warehouse_product__code']
    list_editable = ['is_active', 'quality_grade']
    readonly_fields = ['created_at', 'warehouse_product', 'length_available']
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'fabric_type', 'color', 'batch_number')
        }),
        ('المقاسات والكمية', {
            'fields': ('width', 'cost_per_meter', 'length_available')
        }),
        ('الموقع والجودة', {
            'fields': ('warehouse', 'supplier', 'quality_grade', 'is_active')
        }),
        ('ربط المخزن العام', {
            'fields': ('warehouse_product',),
            'classes': ('collapse',)
        }),
        ('التواريخ', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

@admin.register(FinishedProduct)
class FinishedProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'base_cost', 'selling_price', 'fabric_quantity_per_piece', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'code', 'description']
    list_editable = ['is_active']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('معلومات المنتج', {
            'fields': ('name', 'code', 'category', 'description')
        }),
        ('متطلبات القماش', {
            'fields': ('fabric_per_meter_base', 'fabric_quantity_per_piece')
        }),
        ('التسعير والمتطلبات', {
            'fields': ('base_cost', 'selling_price')
        }),
        ('الحالة والمعلومات', {
            'fields': ('is_active', 'created_by', 'created_at')
        }),
    )

class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1
    autocomplete_fields = ['material']

@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    inlines = [BOMItemInline]
    list_display = ('__str__', 'product', 'size_group', 'version', 'is_active', 'total_cost', 'created_at', 'created_by')
    list_filter = ('is_active', 'product', 'size_group', 'created_at')
    search_fields = ('product__name', 'product__code', 'size_group')
    readonly_fields = ('version', 'parent', 'created_at', 'created_by', 'total_cost')
    list_select_related = ('product', 'created_by')

    def save_model(self, request, obj, form, change):
        if not obj.pk: # If creating a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)       
@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name']
    list_editable = ['is_active']
    
    fieldsets = (
        ('معلومات الفئة', {
            'fields': ('name', 'parent', 'is_active')
        }),
    )

class CuttingTableInline(admin.TabularInline):
    model = CuttingTable
    extra = 1
    readonly_fields = ['total_pieces']

class CutPieceInline(admin.TabularInline):
    model = CutPiece
    extra = 0
    readonly_fields = ['available_quantity']

@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'product', 'batch_number', 'quantity_ordered', 'status', 'priority', 'progress_display', 'created_at']
    list_filter = ['status', 'priority', 'created_at', 'product__category']
    search_fields = ['order_number', 'batch_number', 'product__name']
    readonly_fields = ['batch_number', 'created_at', 'approved_at', 'progress_display', 'total_fabric_required']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('معلومات الأمر', {
            'fields': ('order_number', 'product', 'batch_number', 'quantity_ordered')
        }),
        ('المواد والقماش', {
            'fields': ('textile_stock', 'fabric_meters_allocated', 'total_fabric_required')
        }),
        ('الحالة والأولوية', {
            'fields': ('status', 'priority', 'progress_display')
        }),
        ('التواريخ', {
            'fields': ('start_date', 'expected_completion_date', 'actual_completion_date')
        }),
        ('الموافقات', {
            'fields': ('created_by', 'approved_by', 'created_at', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    def progress_display(self, obj):
        progress = obj.progress_percentage
        color = 'green' if progress == 100 else 'orange' if progress >= 50 else 'red'
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0; border-radius: 3px;">'
            '<div style="width: {}%; background-color: {}; height: 20px; border-radius: 3px; text-align: center; color: white;">'
            '{}%</div></div>',
            progress, color, progress
        )
    progress_display.short_description = 'التقدم'

@admin.register(CuttingProcess)
class CuttingProcessAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'cutting_date', 'cutter', 'total_fabric_used', 'total_pieces_cut', 'fabric_waste', 'is_completed']
    list_filter = ['is_completed', 'cutting_date', 'cutter']
    search_fields = ['production_order__order_number', 'production_order__batch_number']
    readonly_fields = ['completed_at']
    inlines = [CuttingTableInline, CutPieceInline]
    
    fieldsets = (
        ('معلومات العملية', {
            'fields': ('production_order', 'cutting_date', 'cutter')
        }),
        ('الكميات والقياسات', {
            'fields': ('total_fabric_used', 'total_pieces_cut', 'fabric_waste')
        }),
        ('الحالة', {
            'fields': ('is_completed', 'completed_at', 'notes')
        }),
    )

@admin.register(ExternalManufacturer)
class ExternalManufacturerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'price_per_piece', 'quality_rating', 'total_orders_display', 'is_active']
    list_filter = ['is_active', 'quality_rating']
    search_fields = ['name', 'contact_person', 'phone']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'total_orders_display', 'average_defect_rate_display']
    
    fieldsets = (
        ('معلومات المصنع', {
            'fields': ('name', 'contact_person', 'phone', 'address')
        }),
        ('التسعير والجودة', {
            'fields': ('price_per_piece', 'quality_rating', 'payment_terms_days')
        }),
        ('الإحصائيات', {
            'fields': ('total_orders_display', 'average_defect_rate_display'),
            'classes': ('collapse',)
        }),
        ('الحالة', {
            'fields': ('is_active', 'created_at')
        }),
    )
    
    def total_orders_display(self, obj):
        return obj.total_orders
    total_orders_display.short_description = 'إجمالي الأوامر'
    
    def average_defect_rate_display(self, obj):
        rate = obj.average_defect_rate
        color = 'red' if rate > 5 else 'orange' if rate > 2 else 'green'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    average_defect_rate_display.short_description = 'متوسط معدل العيوب'

class AssembledGarmentInline(admin.TabularInline):
    model = AssembledGarment
    extra = 0
    readonly_fields = ['product_code']

@admin.register(AssemblyProcess)
class AssemblyProcessAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'assembly_type', 'external_manufacturer', 'quantity_sent', 'quantity_received', 'defect_rate_display', 'is_completed']
    list_filter = ['assembly_type', 'is_completed', 'external_manufacturer']
    search_fields = ['production_order__order_number', 'external_manufacturer__name']
    readonly_fields = ['actual_completion_date', 'defect_rate_display', 'loss_rate_display']
    inlines = [AssembledGarmentInline]
    
    fieldsets = (
        ('معلومات التجميع', {
            'fields': ('production_order', 'assembly_type', 'external_manufacturer', 'assembler')
        }),
        ('الكميات', {
            'fields': ('quantity_sent', 'quantity_received', 'defects_count', 'losses_count')
        }),
        ('المواد والتكاليف', {
            'fields': ('thread_consumption', 'thread_cost', 'assembly_cost')
        }),
        ('التواريخ', {
            'fields': ('start_date', 'expected_completion_date', 'actual_completion_date')
        }),
        ('الإحصائيات', {
            'fields': ('defect_rate_display', 'loss_rate_display'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes', 'defect_notes', 'is_completed')
        }),
    )
    
    def defect_rate_display(self, obj):
        rate = obj.defect_rate
        color = 'red' if rate > 5 else 'orange' if rate > 2 else 'green'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    defect_rate_display.short_description = 'معدل العيوب'
    
    def loss_rate_display(self, obj):
        rate = obj.loss_rate
        color = 'red' if rate > 3 else 'orange' if rate > 1 else 'green'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    loss_rate_display.short_description = 'معدل الفاقد'

class DyedGarmentInline(admin.TabularInline):
    model = DyedGarment
    extra = 0
    readonly_fields = ['product_code']

@admin.register(DyeingProcess)
class DyeingProcessAdmin(admin.ModelAdmin):
    list_display = ['assembly_process', 'dyeing_facility', 'color_specification', 'quantity_sent', 'quantity_received', 'loss_rate_display', 'is_completed']
    list_filter = ['is_completed', 'dyeing_facility', 'sent_date']
    search_fields = ['assembly_process__production_order__order_number', 'color_specification', 'dyeing_facility']
    readonly_fields = ['actual_return_date', 'total_dyeing_cost', 'loss_rate_display']
    inlines = [DyedGarmentInline]
    
    fieldsets = (
        ('معلومات الصباغة', {
            'fields': ('assembly_process', 'dyeing_facility', 'color_specification')
        }),
        ('الكميات والتكاليف', {
            'fields': ('quantity_sent', 'quantity_received', 'losses_count', 'dyeing_cost_per_piece', 'total_dyeing_cost')
        }),
        ('التواريخ', {
            'fields': ('sent_date', 'expected_return_date', 'actual_return_date')
        }),
        ('الإحصائيات', {
            'fields': ('loss_rate_display',),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes', 'is_completed')
        }),
    )
    
    def loss_rate_display(self, obj):
        rate = obj.loss_rate
        color = 'red' if rate > 3 else 'orange' if rate > 1 else 'green'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    loss_rate_display.short_description = 'معدل الفاقد'


class FinalProductInline(admin.TabularInline):
    model = FinalProduct
    extra = 0
    readonly_fields = ['product_code', 'total_production_cost', 'cost_per_piece', 'stored_date']

@admin.register(FinishingProcess)
class FinishingProcessAdmin(admin.ModelAdmin):
    list_display = ['dyeing_process', 'supervisor', 'quantity_input', 'quantity_output', 'completion_percentage_display', 'defect_rate_display', 'is_completed']
    list_filter = ['is_completed', 'supervisor', 'start_date']
    search_fields = ['dyeing_process__assembly_process__production_order__order_number']
    readonly_fields = ['actual_completion_date', 'total_finishing_cost', 'completion_percentage_display', 'defect_rate_display']
    inlines = [FinalProductInline]
    
    fieldsets = (
        ('معلومات التشطيب', {
            'fields': ('dyeing_process', 'supervisor')
        }),
        ('خطوات التشطيب', {
            'fields': (
                'ironing_completed', 'belt_loops_completed', 'buttons_completed',
                'leather_details_completed', 'cleaning_completed', 'pressing_completed',
                'ticketing_completed', 'bagging_completed', 'packaging_completed'
            )
        }),
        ('الكميات والتكاليف', {
            'fields': ('quantity_input', 'quantity_output', 'defects_in_finishing', 'finishing_cost_per_piece', 'total_finishing_cost')
        }),
        ('التواريخ', {
            'fields': ('start_date', 'expected_completion_date', 'actual_completion_date')
        }),
        ('الإحصائيات', {
            'fields': ('completion_percentage_display', 'defect_rate_display'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes', 'is_completed')
        }),
    )
    
    def completion_percentage_display(self, obj):
        percentage = obj.completion_percentage
        color = 'green' if percentage == 100 else 'orange' if percentage >= 50 else 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, percentage)
    completion_percentage_display.short_description = 'نسبة الإكمال'
    
    def defect_rate_display(self, obj):
        rate = obj.defect_rate
        color = 'red' if rate > 5 else 'orange' if rate > 2 else 'green'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    defect_rate_display.short_description = 'معدل العيوب'

@admin.register(FinalProduct)
class FinalProductAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'size', 'quantity', 'quality_grade', 'warehouse', 'cost_per_piece', 'total_production_cost', 'stored_date']
    list_filter = ['quality_grade', 'warehouse', 'stored_date']
    search_fields = ['product_code', 'batch_info']
    readonly_fields = ['product_code', 'batch_info', 'total_production_cost', 'cost_per_piece', 'stored_date']
    
    fieldsets = (
        ('معلومات المنتج', {
            'fields': ('product_code', 'size', 'quantity', 'quality_grade')
        }),
        ('التخزين', {
            'fields': ('warehouse', 'stored_by', 'stored_date', 'expiry_date')
        }),
        ('التكاليف', {
            'fields': ('total_production_cost', 'cost_per_piece')
        }),
        ('معلومات الدفعة', {
            'fields': ('batch_info',),
            'classes': ('collapse',)
        }),
    )

@admin.register(ProcessDocument)
class ProcessDocumentAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'document_type', 'document_number', 'title', 'created_by', 'created_at']
    list_filter = ['document_type', 'created_at', 'created_by']
    search_fields = ['production_order__order_number', 'document_number', 'title']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('معلومات المستند', {
            'fields': ('production_order', 'document_type', 'document_number', 'title')
        }),
        ('المحتوى', {
            'fields': ('content',)
        }),
        ('معلومات الإنشاء', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ExitPermit)
class ExitPermitAdmin(admin.ModelAdmin):
    list_display = ['permit_number', 'production_order', 'permit_type', 'quantity', 'destination', 'status', 'requested_at', 'is_expired_display']
    list_filter = ['permit_type', 'status', 'requested_at']
    search_fields = ['permit_number', 'production_order__order_number', 'destination']
    readonly_fields = ['permit_number', 'requested_at', 'approved_at', 'used_at', 'is_expired_display', 'can_be_used_display']
    
    fieldsets = (
        ('معلومات التصريح', {
            'fields': ('permit_number', 'production_order', 'permit_type')
        }),
        ('تفاصيل التصريح', {
            'fields': ('items_description', 'quantity', 'destination', 'purpose')
        }),
        ('الحالة والموافقات', {
            'fields': ('status', 'requested_by', 'approved_by')
        }),
        ('التواريخ', {
            'fields': ('requested_at', 'approved_at', 'valid_until', 'used_at')
        }),
        ('الحالة', {
            'fields': ('is_expired_display', 'can_be_used_display'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
    )
    
    def is_expired_display(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        return format_html('<span style="color: green;">ساري</span>')
    is_expired_display.short_description = 'حالة الصلاحية'
    
    def can_be_used_display(self, obj):
        if obj.can_be_used:
            return format_html('<span style="color: green;">يمكن الاستخدام</span>')
        return format_html('<span style="color: red;">لا يمكن الاستخدام</span>')
    can_be_used_display.short_description = 'إمكانية الاستخدام'

@admin.register(ReceiptConfirmation)
class ReceiptConfirmationAdmin(admin.ModelAdmin):
    list_display = ['exit_permit', 'received_by_name', 'quantity_received', 'quantity_variance_display', 'quality_check_passed', 'received_at']
    list_filter = ['quality_check_passed', 'received_at']
    search_fields = ['exit_permit__permit_number', 'received_by_name', 'company_representative']
    readonly_fields = ['received_at', 'quantity_variance_display']
    
    fieldsets = (
        ('معلومات الاستلام', {
            'fields': ('exit_permit', 'received_by_name', 'company_representative')
        }),
        ('تفاصيل الاستلام', {
            'fields': ('quantity_received', 'quantity_variance_display', 'condition_notes', 'quality_check_passed')
        }),
        ('التوقيع والتأكيد', {
            'fields': ('received_by_signature', 'confirmed_by', 'received_at')
        }),
        ('المرفقات', {
            'fields': ('photo_evidence', 'additional_documents'),
            'classes': ('collapse',)
        }),
    )
    
    def quantity_variance_display(self, obj):
        variance = obj.quantity_variance
        if variance == 0:
            return format_html('<span style="color: green;">0 (مطابق)</span>')
        elif variance > 0:
            return format_html('<span style="color: blue;">+{} (زيادة)</span>', variance)
        else:
            return format_html('<span style="color: red;">{} (نقص)</span>', variance)
    quantity_variance_display.short_description = 'فرق الكمية'

@admin.register(ProductionCostAnalysis)
class ProductionCostAnalysisAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'total_production_cost', 'cost_per_piece', 'material_cost_percentage_display', 'waste_percentage_display', 'analysis_date']
    list_filter = ['analysis_date', 'analyzed_by']
    search_fields = ['production_order__order_number']
    readonly_fields = ['analysis_date', 'last_updated', 'material_cost_percentage_display', 'process_cost_percentage_display', 'waste_percentage_display']
    
    fieldsets = (
        ('معلومات التحليل', {
            'fields': ('production_order', 'analyzed_by', 'analysis_date', 'last_updated')
        }),
        ('تكاليف المواد', {
            'fields': ('fabric_cost', 'thread_cost', 'accessories_cost', 'total_material_cost')
        }),
        ('تكاليف العمليات', {
            'fields': ('cutting_cost', 'assembly_cost', 'dyeing_cost', 'finishing_cost', 'total_process_cost')
        }),
        ('التكاليف الإضافية', {
            'fields': ('transportation_cost', 'overhead_cost', 'quality_control_cost', 'total_additional_cost')
        }),
        ('الفاقد والعيوب', {
            'fields': ('waste_cost', 'defect_cost')
        }),
        ('الإجماليات', {
            'fields': ('total_production_cost', 'cost_per_piece')
        }),
        ('النسب المئوية', {
            'fields': ('material_cost_percentage_display', 'process_cost_percentage_display', 'waste_percentage_display'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
    )
    
    def material_cost_percentage_display(self, obj):
        percentage = obj.material_cost_percentage
        return format_html('{:.1f}%', percentage)
    material_cost_percentage_display.short_description = 'نسبة تكلفة المواد'
    
    def process_cost_percentage_display(self, obj):
        percentage = obj.process_cost_percentage
        return format_html('{:.1f}%', percentage)
    process_cost_percentage_display.short_description = 'نسبة تكلفة العمليات'
    
    def waste_percentage_display(self, obj):
        percentage = obj.waste_percentage
        color = 'red' if percentage > 10 else 'orange' if percentage > 5 else 'green'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, percentage)
    waste_percentage_display.short_description = 'نسبة الفاقد'

@admin.register(QualityControlCheck)
class QualityControlCheckAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'check_type', 'overall_grade', 'pass_rate_display', 'failure_rate_display', 'inspector', 'check_date', 'approved']
    list_filter = ['check_type', 'overall_grade', 'approved', 'check_date', 'inspector']
    search_fields = ['production_order__order_number', 'defect_description']
    readonly_fields = ['pass_rate_display', 'failure_rate_display']
    
    fieldsets = (
        ('معلومات الفحص', {
            'fields': ('production_order', 'check_type', 'check_date', 'inspector')
        }),
        ('نتائج الفحص', {
            'fields': ('items_checked', 'items_passed', 'items_failed', 'overall_grade')
        }),
        ('الإحصائيات', {
            'fields': ('pass_rate_display', 'failure_rate_display'),
            'classes': ('collapse',)
        }),
        ('تفاصيل العيوب', {
            'fields': ('defect_description', 'corrective_actions')
        }),
        ('الموافقة', {
            'fields': ('approved', 'approved_by')
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
    )
    
    def pass_rate_display(self, obj):
        rate = obj.pass_rate
        color = 'green' if rate >= 95 else 'orange' if rate >= 85 else 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    pass_rate_display.short_description = 'معدل النجاح'
    
    def failure_rate_display(self, obj):
        rate = obj.failure_rate
        color = 'red' if rate >= 15 else 'orange' if rate >= 5 else 'green'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    failure_rate_display.short_description = 'معدل الفشل'

@admin.register(ProductionReport)
class ProductionReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'period_start', 'period_end', 'total_orders', 'completion_rate_display', 'average_quality_score', 'generated_at']
    list_filter = ['report_type', 'generated_at', 'generated_by']
    search_fields = ['title', 'report_content']
    readonly_fields = ['generated_at', 'completion_rate_display', 'average_cost_per_piece_display']
    date_hierarchy = 'generated_at'
    
    fieldsets = (
        ('معلومات التقرير', {
            'fields': ('title', 'report_type', 'period_start', 'period_end')
        }),
        ('البيانات الأساسية', {
            'fields': ('total_orders', 'completed_orders', 'total_pieces_produced', 'total_production_cost')
        }),
        ('مؤشرات الجودة', {
            'fields': ('average_quality_score', 'defect_rate', 'waste_rate')
        }),
        ('الإحصائيات المحسوبة', {
            'fields': ('completion_rate_display', 'average_cost_per_piece_display'),
            'classes': ('collapse',)
        }),
        ('محتوى التقرير', {
            'fields': ('report_content', 'recommendations')
        }),
        ('معلومات الإنشاء', {
            'fields': ('generated_by', 'generated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def completion_rate_display(self, obj):
        rate = obj.completion_rate
        color = 'green' if rate >= 90 else 'orange' if rate >= 70 else 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    completion_rate_display.short_description = 'معدل الإكمال'
    
    def average_cost_per_piece_display(self, obj):
        cost = obj.average_cost_per_piece
        return format_html('{:.2f} جنيه', cost)
    average_cost_per_piece_display.short_description = 'متوسط تكلفة القطعة'

# تخصيص عنوان الإدارة
admin.site.site_header = "إدارة نظام الإنتاج - Mekawy ERP"
admin.site.site_title = "إدارة الإنتاج"
admin.site.index_title = "لوحة تحكم الإنتاج"

# إضافة أكشن مخصص لحساب التكاليف
def calculate_production_costs(modeladmin, request, queryset):
    """حساب تكاليف الإنتاج للأوامر المحددة"""
    for order in queryset:
        analysis, created = ProductionCostAnalysis.objects.get_or_create(
            production_order=order,
            defaults={'analyzed_by': request.user}
        )
        analysis.calculate_totals()
    
    count = queryset.count()
    modeladmin.message_user(request, f'تم حساب التكاليف لـ {count} أمر إنتاج.')

calculate_production_costs.short_description = "حساب تكاليف الإنتاج"

# إضافة الأكشن إلى ProductionOrderAdmin
ProductionOrderAdmin.actions = [calculate_production_costs]

# إضافة أكشن لإنشاء تقارير
def generate_production_report(modeladmin, request, queryset):
    """إنشاء تقرير إنتاج للأوامر المحددة"""
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    # حساب الإحصائيات
    total_orders = queryset.count()
    completed_orders = queryset.filter(status='completed').count()
    total_pieces = queryset.aggregate(
        total=Sum('quantity_ordered')
    )['total'] or 0
    
    # إنشاء التقرير
    report = ProductionReport.objects.create(
        report_type='order_summary',
        title=f'تقرير أوامر الإنتاج - {today}',
        period_start=week_ago,
        period_end=today,
        total_orders=total_orders,
        completed_orders=completed_orders,
        total_pieces_produced=total_pieces,
        report_content=f'تقرير يشمل {total_orders} أمر إنتاج، منها {completed_orders} مكتمل.',
        generated_by=request.user
    )
    
    modeladmin.message_user(request, f'تم إنشاء التقرير: {report.title}')

generate_production_report.short_description = "إنشاء تقرير إنتاج"

# إضافة الأكشن إلى ProductionOrderAdmin
ProductionOrderAdmin.actions.append(generate_production_report)


@admin.register(SizeGroup)
class SizeGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_sizes_display')
    search_fields = ('name',)

    def get_sizes_display(self, obj):
        return ", ".join(obj.sizes)
    get_sizes_display.short_description = 'Sizes'