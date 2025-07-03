from django.urls import path
from . import views

app_name = 'warehouses'

urlpatterns = [
    # Dashboard
    path('', views.WarehouseDashboardView.as_view(), name='dashboard'),
    
    path('inventory/count/', views.InventoryCountView.as_view(), name='inventory_count'), # New URL
    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/add/', views.CategoryCreateView.as_view(), name='category_add'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category_detail'),
    path('categories/<int:pk>/edit/', views.CategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),
    
    # Units
    path('units/', views.UnitListView.as_view(), name='unit_list'),
    path('units/add/', views.UnitCreateView.as_view(), name='unit_add'),
    path('units/<int:pk>/edit/', views.UnitUpdateView.as_view(), name='unit_edit'),
    path('units/<int:pk>/delete/', views.UnitDeleteView.as_view(), name='unit_delete'),
    
    # Unit Conversions
    path('unit-conversions/', views.UnitConversionListView.as_view(), name='unit_conversion_list'),
    path('unit-conversions/add/', views.UnitConversionCreateView.as_view(), name='unit_conversion_add'),
    path('unit-conversions/<int:pk>/edit/', views.UnitConversionUpdateView.as_view(), name='unit_conversion_edit'),
    path('unit-conversions/<int:pk>/delete/', views.UnitConversionDeleteView.as_view(), name='unit_conversion_delete'),
    # Warehouses
    path('list/', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('add/', views.WarehouseCreateView.as_view(), name='warehouse_add'),
    path('warehouse/<int:pk>/', views.WarehouseDetailView.as_view(), name='warehouse_detail'),
    path('warehouse/<int:pk>/edit/', views.WarehouseUpdateView.as_view(), name='warehouse_edit'),
    path('warehouse/<int:pk>/delete/', views.WarehouseDeleteView.as_view(), name='warehouse_delete'),
    path('warehouse/<int:pk>/export/pdf/', views.WarehouseDetailPDFView.as_view(), name='warehouse_detail_pdf'),

    # Products
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('products/<int:pk>/export/pdf/', views.ProductDetailPDFView.as_view(), name='product_detail_pdf'),

    # Stock
    path('stock/', views.StockListView.as_view(), name='stock_list'),
    path('stock/add/', views.StockCreateView.as_view(), name='stock_add'),
    path('stock/<int:pk>/', views.StockDetailView.as_view(), name='stock_detail'),
    path('stock/<int:pk>/edit/', views.StockUpdateView.as_view(), name='stock_edit'),
    path('stock/low/', views.LowStockView.as_view(), name='low_stock'),
    path('stock/out/', views.OutOfStockView.as_view(), name='out_of_stock'),
    path('stock/low/export/pdf/', views.LowStockPDFView.as_view(), name='low_stock_pdf'), # New URL

    path('stock/<int:pk>/export/pdf/', views.StockItemDetailPDFView.as_view(), name='stock_detail_pdf'), # New URL

    # Stock Movements
    path('stock/movement/', views.StockMovementListView.as_view(), name='movement_list'),
    path('stock/movement/add/', views.StockMovementCreateView.as_view(), name='movement_add'),
    
    # Transfers
    path('transfers/', views.StockTransferListView.as_view(), name='transfer_list'),
    path('transfers/add/', views.StockTransferCreateView.as_view(), name='transfer_add'),
    path('transfers/<int:pk>/', views.StockTransferDetailView.as_view(), name='transfer_detail'),
    path('transfers/<int:pk>/approve/', views.StockTransferApproveView.as_view(), name='transfer_approve'),
    path('transfers/<int:pk>/complete/', views.StockTransferCompleteView.as_view(), name='transfer_complete'),
    path('transfers/pending/', views.StockTransferListView.as_view(), {'status': 'pending'}, name='pending_transfers'),
    # Stock Management
    path('stock/adjustment/', views.StockAdjustmentView.as_view(), name='stock_adjustment'),
    path('stock/alerts/', views.StockAlertsView.as_view(), name='stock_alerts'),
    
    # Export endpoints
    path('export/stock/', views.export_stock_csv, name='export_stock_csv'),
    path('export/movements/', views.export_movements_csv, name='export_movements_csv'),
    path('export/warehouse/<int:warehouse_id>/', views.export_warehouse_csv, name='export_warehouse_csv'),
    path('export/warehouses/', views.export_warehouses_csv, name='export_warehouses_csv'),

    # API endpoints
    path('api/products/search/', views.ProductSearchView.as_view(), name='product_search'),
    path('api/products/generate-code/', views.GenerateProductCodeView.as_view(), name='product_generate_code'),

    path('api/warehouses/search/', views.WarehouseSearchView.as_view(), name='warehouse_search'),
    path('api/stock/search/', views.StockSearchView.as_view(), name='stock_search'),
    path('api/product/<int:product_id>/stock/', views.ProductStockAPIView.as_view(), name='product_stock_api'),
    path('api/warehouse/<int:warehouse_id>/stock/', views.WarehouseStockAPIView.as_view(), name='warehouse_stock_api'),
    path('api/stock/<int:stock_id>/', views.StockItemAPIView.as_view(), name='stock_item_api'),
    path('api/dashboard/', views.warehouse_dashboard_api, name='warehouse_dashboard_api'),
    path('api/barcode/scan/', views.BarcodeStockView.as_view(), name='barcode_scan'),
    path('api/check-existing-stock/', views.CheckExistingStockView.as_view(), name='check_existing_stock'),
    path('api/unit-conversion/', views.UnitConversionAPIView.as_view(), name='unit_conversion_api'),
    

    # Bulk operations
    path('stock/bulk-update/', views.bulk_stock_update, name='bulk_stock_update'),
    path('stock/import/', views.import_stock_csv, name='import_stock_csv'),
    path('stock/quick-adjustment/', views.quick_stock_adjustment, name='quick_stock_adjustment'),
]
