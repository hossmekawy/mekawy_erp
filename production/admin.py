from django.contrib import admin
from .models import (
    SizeGroup, BillOfMaterials, BOMItem, ProductionOrder, CuttingProcess,
    CuttingTable, CutPiece, ExternalManufacturer, AssemblyProcess,
    AssemblyComponent, AssembledGarment, DyeingProcess, DyedGarment,
    FinishingProcess, FinishingComponent, ExitPermit, ReceiptConfirmation,
    ProductionCostAnalysis, QualityControlCheck, ProductionReport, GarmentDraw,
    DrawPiece
)

# Note: This file is now fully aligned with the new model structure.
# All references to deleted models have been removed.
# Autocomplete fields and inlines have been added for a better admin experience.

@admin.register(SizeGroup)
class SizeGroupAdmin(admin.ModelAdmin):
    list_display = ['name']
    # --- FIX: Added search_fields to support autocomplete from other apps ---
    search_fields = ['name']

class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1
    autocomplete_fields = ['material']

@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    inlines = [BOMItemInline]
    list_display = ['product', 'size_group', 'version', 'is_active', 'created_at']
    list_filter = ['is_active', 'product', 'size_group', 'created_at']
    search_fields = ['product__name', 'product__code', 'size_group__name']
    autocomplete_fields = ['product', 'size_group', 'created_by', 'parent']

class CuttingTableInline(admin.TabularInline):
    model = CuttingTable
    extra = 1

class CutPieceInline(admin.TabularInline):
    model = CutPiece
    extra = 0
    readonly_fields = ('available_quantity',)

@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'product', 'batch_number', 'quantity_ordered', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'created_at', 'product']
    search_fields = ['order_number', 'batch_number', 'product__name']
    readonly_fields = ['order_number', 'batch_number', 'created_at', 'approved_at', 'actual_completion_date']
    autocomplete_fields = ['product', 'textile_stock', 'created_by', 'approved_by', 'bom_version']

@admin.register(CuttingProcess)
class CuttingProcessAdmin(admin.ModelAdmin):
    inlines = [CuttingTableInline, CutPieceInline]
    list_display = ['production_order', 'cutting_date', 'cutter', 'total_fabric_used', 'total_pieces_cut', 'is_completed']
    list_filter = ['is_completed', 'cutting_date', 'cutter']
    search_fields = ['production_order__order_number', 'production_order__batch_number']
    readonly_fields = ['completed_at']
    autocomplete_fields = ['production_order', 'cutter']

@admin.register(ExternalManufacturer)
class ExternalManufacturerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'price_per_piece', 'quality_rating', 'is_active', 'created_at']
    list_filter = ['is_active', 'quality_rating']
    search_fields = ['name', 'contact_person', 'phone']
    readonly_fields = ['created_at']

class AssemblyComponentInline(admin.TabularInline):
    model = AssemblyComponent
    extra = 1
    autocomplete_fields = ['material']

class AssembledGarmentInline(admin.TabularInline):
    model = AssembledGarment
    extra = 0

@admin.register(AssemblyProcess)
class AssemblyProcessAdmin(admin.ModelAdmin):
    inlines = [AssemblyComponentInline, AssembledGarmentInline]
    list_display = ['production_order', 'assembly_type', 'external_manufacturer', 'quantity_sent', 'quantity_received', 'is_completed']
    list_filter = ['assembly_type', 'is_completed', 'external_manufacturer']
    search_fields = ['production_order__order_number', 'external_manufacturer__name']
    readonly_fields = ['actual_completion_date']
    autocomplete_fields = ['production_order', 'external_manufacturer', 'assembler']

class DyedGarmentInline(admin.TabularInline):
    model = DyedGarment
    extra = 0

@admin.register(DyeingProcess)
class DyeingProcessAdmin(admin.ModelAdmin):
    inlines = [DyedGarmentInline]
    list_display = ['assembly_process', 'dyeing_facility', 'color_specification', 'quantity_sent', 'quantity_received', 'is_completed']
    list_filter = ['is_completed', 'dyeing_facility']
    search_fields = ['assembly_process__production_order__order_number', 'dyeing_facility']
    autocomplete_fields = ['assembly_process']

class FinishingComponentInline(admin.TabularInline):
    model = FinishingComponent
    extra = 1
    autocomplete_fields = ['material']

@admin.register(FinishingProcess)
class FinishingProcessAdmin(admin.ModelAdmin):
    inlines = [FinishingComponentInline]
    list_display = ['dyeing_process', 'supervisor', 'quantity_input', 'quantity_output', 'is_completed']
    # --- FIX: Added search_fields to support autocomplete from other apps ---
    search_fields = ['dyeing_process__assembly_process__production_order__order_number', 'supervisor__username']
    autocomplete_fields = ['dyeing_process', 'supervisor', 'destination_warehouse', 'external_manufacturer', 'finisher']

@admin.register(ExitPermit)
class ExitPermitAdmin(admin.ModelAdmin):
    list_display = ['permit_number', 'production_order', 'permit_type', 'status', 'requested_at']
    search_fields = ['permit_number', 'production_order__order_number']
    autocomplete_fields = ['production_order', 'requested_by', 'approved_by']

@admin.register(ReceiptConfirmation)
class ReceiptConfirmationAdmin(admin.ModelAdmin):
    list_display = ['exit_permit', 'received_by_name', 'received_at']
    search_fields = ['exit_permit__permit_number', 'received_by_name']
    autocomplete_fields = ['exit_permit', 'confirmed_by']

@admin.register(ProductionCostAnalysis)
class ProductionCostAnalysisAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'total_production_cost', 'cost_per_piece', 'analysis_date']
    search_fields = ['production_order__order_number']
    autocomplete_fields = ['production_order', 'analyzed_by']

@admin.register(QualityControlCheck)
class QualityControlCheckAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'check_type', 'overall_grade', 'inspector', 'check_date', 'approved']
    list_filter = ['check_type', 'overall_grade', 'approved', 'check_date']
    search_fields = ['production_order__order_number', 'inspector__username']
    autocomplete_fields = ['production_order', 'cutting_process', 'assembly_process', 'dyeing_process', 'finishing_process', 'inspector', 'approved_by']

@admin.register(ProductionReport)
class ProductionReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'period_start', 'period_end', 'generated_at']
    list_filter = ['report_type']
    search_fields = ['title']
    autocomplete_fields = ['generated_by']

@admin.register(GarmentDraw)
class GarmentDrawAdmin(admin.ModelAdmin):
    list_display = ['bom', 'size', 'created_at']
    search_fields = ['bom__product__name', 'size']
    autocomplete_fields = ['bom', 'created_by']

@admin.register(DrawPiece)
class DrawPieceAdmin(admin.ModelAdmin):
    list_display = ['draw', 'name', 'quantity']
    search_fields = ['name', 'draw__bom__product__name']
    autocomplete_fields = ['draw']

# These models are simple and don't need complex admin panels, but registering them is good practice.
@admin.register(CuttingTable)
class CuttingTableAdmin(admin.ModelAdmin):
    list_display = ['cutting_process', 'fabric_length', 'layers_count', 'total_pieces']
    search_fields = ['cutting_process__production_order__order_number']

@admin.register(CutPiece)
class CutPieceAdmin(admin.ModelAdmin):
    list_display = ['cutting_process', 'piece_type', 'size', 'quantity', 'available_quantity']
    search_fields = ['cutting_process__production_order__order_number', 'piece_type', 'size']

@admin.register(AssemblyComponent)
class AssemblyComponentAdmin(admin.ModelAdmin):
    list_display = ['assembly_process', 'material', 'quantity_sent']
    search_fields = ['assembly_process__production_order__order_number', 'material__name']

@admin.register(AssembledGarment)
class AssembledGarmentAdmin(admin.ModelAdmin):
    list_display = ['assembly_process', 'size', 'quantity']
    search_fields = ['assembly_process__production_order__order_number', 'size']

@admin.register(DyedGarment)
class DyedGarmentAdmin(admin.ModelAdmin):
    list_display = ['dyeing_process', 'size', 'quantity', 'color_quality']
    search_fields = ['dyeing_process__assembly_process__production_order__order_number', 'size']

@admin.register(FinishingComponent)
class FinishingComponentAdmin(admin.ModelAdmin):
    list_display = ['finishing_process', 'material', 'quantity_sent']
    search_fields = ['finishing_process__dyeing_process__assembly_process__production_order__order_number', 'material__name']

# Customize admin site titles
admin.site.site_header = "إدارة نظام الإنتاج - Mekawy ERP"
admin.site.site_title = "إدارة الإنتاج"
admin.site.index_title = "لوحة تحكم الإنتاج"
