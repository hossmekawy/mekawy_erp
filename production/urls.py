from django.urls import path, include
from . import views
from .blueprints import bom_exports_blueprint, draw_blueprint, category_size_blueprint, cost_analysis_exports_blueprint

app_name = 'production'

# URL patterns for specific sub-modules, kept for organization.

draw_patterns = [
    path('', draw_blueprint.GarmentDrawListView.as_view(), name='draw_list'),
    path('create/', draw_blueprint.GarmentDrawCreateView.as_view(), name='draw_create'),
    path('<int:pk>/', draw_blueprint.GarmentDrawDetailView.as_view(), name='draw_detail'),
    path('<int:pk>/update/', draw_blueprint.GarmentDrawUpdateView.as_view(), name='draw_update'),
    path('<int:pk>/delete/', draw_blueprint.GarmentDrawDeleteView.as_view(), name='draw_delete'),
    path('<int:pk>/print/', draw_blueprint.print_draw_pdf, name='draw_print_pdf'),
    path('ajax/get-sizes-for-bom/', draw_blueprint.get_sizes_for_bom_ajax, name='ajax_get_sizes_for_bom'),
    path('bulk-print-pdf/', draw_blueprint.bulk_print_draw_pdf, name='draw_bulk_print_pdf'),
]

manufacturer_patterns = [
    path('', views.ExternalManufacturerListView.as_view(), name='manufacturer_list'),
    path('create/', views.ExternalManufacturerCreateView.as_view(), name='manufacturer_create'),
    path('<int:pk>/', views.ExternalManufacturerDetailView.as_view(), name='manufacturer_detail'),
    path('<int:pk>/update/', views.ExternalManufacturerUpdateView.as_view(), name='manufacturer_update'),
    path('<int:pk>/delete/', views.ExternalManufacturerDeleteView.as_view(), name='manufacturer_delete'),
]

exit_permit_patterns = [
    path('', views.ExitPermitListView.as_view(), name='exit_permit_list'),
    path('create/', views.ExitPermitCreateView.as_view(), name='exit_permit_create'),
    path('<int:pk>/', views.ExitPermitDetailView.as_view(), name='exit_permit_detail'),
    path('<int:pk>/approve/', views.approve_exit_permit, name='exit_permit_approve'),
    path('<int:pk>/use/', views.use_exit_permit, name='exit_permit_use'),
    path('<int:pk>/print/', views.print_exit_permit_pdf, name='exit_permit_print_pdf'),
    path('receipt/<int:pk>/', views.ExitPermitReceiptView.as_view(), name='exit_permit_receipt'),
    path('receipt/<int:pk>/print/', views.print_exit_permit_receipt_pdf, name='exit_permit_receipt_print_pdf'),
]

quality_patterns = [
    path('', views.QualityControlListView.as_view(), name='quality_list'),
    path('create/', views.QualityControlCreateView.as_view(), name='quality_create'),
    path('<int:pk>/', views.QualityControlDetailView.as_view(), name='quality_detail'),
    path('<int:pk>/update/', views.QualityControlUpdateView.as_view(), name='quality_update'),
    path('<int:pk>/approve/', views.approve_quality_check, name='quality_approve'),
    path('<int:pk>/delete/', views.QualityControlDeleteView.as_view(), name='quality_delete'),
]

# Main URL Patterns for the Production App
urlpatterns = [
    path('', views.ProductionDashboardView.as_view(), name='dashboard'),

    # --- INCLUDED URLS FOR SUB-MODULES ---
    path('draws/', include((draw_patterns, 'draws'))),
    path('manufacturers/', include((manufacturer_patterns, 'manufacturers'))),
    path('exit-permits/', include((exit_permit_patterns, 'exit_permits'))),
    path('quality/', include((quality_patterns, 'quality'))),

    # --- CORRECTED: Category & Size Group Management ---
    path('settings/management/', category_size_blueprint.category_size_management_view, name='category_size_management'),
    path('ajax/categories/create/', category_size_blueprint.create_category_ajax, name='create_category_ajax'),
    path('ajax/categories/<int:category_id>/update/', category_size_blueprint.update_category_ajax, name='update_category_ajax'),
    path('ajax/categories/<int:category_id>/delete/', category_size_blueprint.delete_category_ajax, name='delete_category_ajax'),
    path('ajax/categories/<int:category_id>/get/', category_size_blueprint.get_category_ajax, name='get_category_ajax'),
    path('ajax/categories/<int:category_id>/toggle-status/', category_size_blueprint.toggle_category_status_ajax, name='toggle_category_status_ajax'),

    path('ajax/size-groups/create/', category_size_blueprint.create_size_group_ajax, name='create_size_group_ajax'),
    path('ajax/size-groups/<int:size_group_id>/update/', category_size_blueprint.update_size_group_ajax, name='update_size_group_ajax'),
    path('ajax/size-groups/<int:size_group_id>/delete/', category_size_blueprint.delete_size_group_ajax, name='delete_size_group_ajax'),
    path('ajax/size-groups/<int:size_group_id>/get/', category_size_blueprint.get_size_group_ajax, name='get_size_group_ajax'),
    path('export/size-groups/', category_size_blueprint.export_size_groups, name='export_size_groups'),
    path('export/categories/', category_size_blueprint.export_categories, name='export_categories'),

    # Production Orders
    path('orders/', views.ProductionOrderListView.as_view(), name='order_list'),
    path('orders/create/', views.ProductionOrderCreateView.as_view(), name='order_create'),
    path('orders/export/', views.export_orders, name='export_orders'),

    path('orders/<int:pk>/', views.ProductionOrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/update/', views.ProductionOrderUpdateView.as_view(), name='order_update'),
    path('orders/<int:pk>/delete/', views.ProductionOrderDeleteView.as_view(), name='order_delete'),
    path('orders/<int:pk>/approve/', views.approve_production_order, name='order_approve'),
    path('orders/<int:pk>/print/', views.print_production_order_pdf, name='print_production_order'),

    # Production Processes
    path('cutting/', views.CuttingProcessListView.as_view(), name='cutting_list'),
    path('cutting/create/', views.CuttingProcessCreateView.as_view(), name='cutting_create'),
    path('cutting/<int:pk>/', views.CuttingProcessDetailView.as_view(), name='cutting_detail'),
    path('cutting/<int:pk>/update/', views.CuttingProcessUpdateView.as_view(), name='cutting_update'),
    path('cutting/<int:pk>/complete/', views.complete_cutting_process, name='cutting_complete'),
    path('cutting/<int:pk>/print_pdf/', views.print_cutting_sheet_pdf, name='cutting_sheet_print_pdf'),

    path('assembly/', views.AssemblyProcessListView.as_view(), name='assembly_list'),
    path('assembly/create/', views.AssemblyProcessCreateView.as_view(), name='assembly_create'),
    path('assembly/<int:pk>/', views.AssemblyProcessDetailView.as_view(), name='assembly_detail'),
    path('assembly/<int:pk>/update/', views.AssemblyProcessUpdateView.as_view(), name='assembly_update'),
    path('assembly/<int:pk>/receive/', views.receive_assembly_process, name='assembly_receive'),
    path('assembly/<int:pk>/print_pdf/', views.print_assembly_detail_pdf, name='assembly_print_pdf'),
    path('assembly/<int:pk>/send-materials/', views.send_additional_materials, name='assembly_send_materials'),

    path('dyeing/', views.DyeingProcessListView.as_view(), name='dyeing_list'),
    path('dyeing/create/', views.DyeingProcessCreateView.as_view(), name='dyeing_create'),
    path('dyeing/<int:pk>/', views.DyeingProcessDetailView.as_view(), name='dyeing_detail'),
    path('dyeing/<int:pk>/update/', views.DyeingProcessUpdateView.as_view(), name='dyeing_update'),
    path('dyeing/<int:pk>/receive/', views.receive_dyeing_process, name='dyeing_receive'),
    path('dyeing/<int:pk>/print_pdf/', views.print_dyeing_process_pdf, name='dyeing_print_pdf'),
    path('dyeing/<int:pk>/delete/', views.DyeingProcessDeleteView.as_view(), name='dyeing_delete'),

    path('finishing/', views.FinishingProcessListView.as_view(), name='finishing_list'),
    path('finishing/create/', views.FinishingProcessCreateView.as_view(), name='finishing_create'),
    path('finishing/<int:pk>/', views.FinishingProcessDetailView.as_view(), name='finishing_detail'),
    path('finishing/<int:pk>/update/', views.FinishingProcessUpdateView.as_view(), name='finishing_update'),
    path('finishing/<int:pk>/delete/', views.FinishingProcessDeleteView.as_view(), name='finishing_delete'),
    path('finishing/<int:pk>/receive/', views.receive_finishing_process, name='finishing_receive'),
    path('finishing/<int:pk>/print_pdf/', views.print_finishing_process_pdf, name='finishing_print_pdf'),

    # Bill of Materials
    path('bom/', views.BillOfMaterialsListView.as_view(), name='bom_list'),
    path('bom/create/', views.BillOfMaterialsCreateView.as_view(), name='bom_create'),
    path('bom/<int:pk>/', views.BillOfMaterialsDetailView.as_view(), name='bom_detail'),
    path('bom/<int:pk>/update/', views.BillOfMaterialsUpdateView.as_view(), name='bom_update'),
    path('bom/<int:pk>/delete/', views.BillOfMaterialsDeleteView.as_view(), name='bom_delete'),
    path('bom/<int:pk>/copy/', views.copy_bill_of_materials, name='bom_copy'),
    
    path('bom/<int:bom_id>/export/', include(bom_exports_blueprint.urlpatterns)),

    # Cost Analysis
    path('cost-analysis/', views.CostAnalysisListView.as_view(), name='cost_analysis_list'),
    path('cost-analysis/create/<int:order_id>/', views.CostAnalysisCreateView.as_view(), name='cost_analysis_create'),
    path('cost-analysis/<int:pk>/', views.CostAnalysisDetailView.as_view(), name='cost_analysis_detail'),
    path('cost-analysis/<int:pk>/update/', views.CostAnalysisUpdateView.as_view(), name='cost_analysis_update'),
    path('cost-analysis/select-order/', views.CostAnalysisSelectOrderView.as_view(), name='cost_analysis_select_order'), 
    path('cost-analysis/<int:pk>/export/', include((cost_analysis_exports_blueprint.urlpatterns, 'cost_analysis_exports'))),

    # --- CORRECTED AJAX URLS ---
    path('ajax/get-stock-item-details/', views.get_stock_item_details_ajax, name='get_stock_item_details_ajax'),
    path('ajax/get-size-group-for-product/', views.get_size_group_for_product_ajax, name='get_size_group_for_product_ajax'),
    path('ajax/search-raw-materials/', views.search_raw_materials_ajax, name='search_raw_materials_ajax'),
    path('ajax/generate-batch/', views.batch_generator_view, name='batch_generator_view'),
    path('ajax/get-order-details/', views.get_order_details_ajax, name='get_order_details_ajax'),
    path('ajax/get-bom-for-assembly/', views.ajax_get_bom_for_assembly, name='ajax_get_bom_for_assembly'),
    path('ajax/get-finishing-bom-components/', views.ajax_get_finishing_bom_components_for_dyeing, name='ajax_get_finishing_bom_components'),
    path('ajax/update-process-status/', views.update_process_status_ajax, name='update_process_status_ajax'),
    
    path('ajax/calculate-fabric-requirement/', views.calculate_fabric_requirement_ajax, name='calculate_fabric_requirement_ajax'),
    path('ajax/get-draws-for-order/', views.get_draws_for_order_ajax, name='ajax_get_draws_for_order'),

    # =============================================================================
    #  FIX: ADD THE MISSING AJAX URL PATTERNS HERE
    # =============================================================================
    path('ajax/get-bom-components-for-order/', views.ajax_get_bom_components_for_order, name='ajax_get_bom_components_for_order'),
    path('ajax/get-stock-for-material-in-warehouse/', views.get_stock_for_material_in_warehouse_ajax, name='ajax_get_stock_for_material_in_warehouse'),
]