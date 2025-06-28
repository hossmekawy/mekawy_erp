from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    # Supplier URLs
    path('', views.SupplierListView.as_view(), name='list'),
    path('<int:pk>/', views.SupplierDetailView.as_view(), name='detail'),
    path('<int:pk>/toggle-status/', views.toggle_supplier_status, name='toggle_status'),
    path('create/', views.SupplierCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='edit'),
    path('dashboard/', views.SupplierDashboardView.as_view(), name='dashboard'),
    path('search/', views.AdvancedSupplierSearchView.as_view(), name='advanced_search'),
    path('performance/', views.SupplierPerformanceView.as_view(), name='performance'),
    path('reports/', views.SupplierReportView.as_view(), name='reports'),
    
    # Purchase Order URLs
    path('purchase-orders/', views.PurchaseOrderListView.as_view(), name='purchase_orders'),
    path('purchase-orders/create/', views.PurchaseOrderCreateView.as_view(), name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/edit/', views.PurchaseOrderUpdateView.as_view(), name='purchase_order_edit'),
    path('purchase-orders/<int:pk>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
    path('purchase-orders/<int:pk>/approve/', views.purchase_order_approve, name='purchase_order_approve'),
    path('purchase-orders/<int:pk>/reject/', views.purchase_order_reject, name='purchase_order_reject'),
    path('purchase-orders/<int:pk>/delete/', views.purchase_order_delete, name='purchase_order_delete'),
    path('purchase-orders/<int:purchase_order_id>/rate/', views.SupplierRatingCreateView.as_view(), name='purchase_order_rate'),

    # Supplier Rating URLs
    path('suppliers/<int:supplier_id>/ratings/', views.SupplierRatingListView.as_view(), name='supplier_ratings'),
    path('suppliers/<int:supplier_id>/ratings/add/', views.SupplierRatingCreateView.as_view(), name='supplier_rating_add'),
    path('suppliers/<int:supplier_id>/ratings/quick/', views.quick_supplier_rating, name='supplier_rating_quick'),
    path('ratings/', views.SupplierRatingListView.as_view(), name='all_ratings'),
    path('ratings/<int:pk>/', views.SupplierRatingDetailView.as_view(), name='supplier_rating_detail'),
    path('ratings/<int:pk>/edit/', views.SupplierRatingUpdateView.as_view(), name='supplier_rating_edit'),
    path('ratings/<int:pk>/delete/', views.SupplierRatingDeleteView.as_view(), name='supplier_rating_delete'),

    # Payment URLs
    path('payments/', views.PaymentListView.as_view(), name='payments'),
    
    # API URLs
    path('api/search/', views.supplier_search_api, name='api_search'),
    path('api/<int:pk>/stats/', views.supplier_stats_api, name='api_stats'),
    path('api/<int:pk>/update-rating/', views.update_supplier_rating, name='api_update_rating'),
    path('api/purchase-orders/<int:pk>/items/', views.purchase_order_items_api, name='api_po_items'),
    path('api/bulk-update/', views.bulk_update_suppliers, name='api_bulk_update'),
    path('api/products/', views.products_api, name='api_products'),
    path('api/suppliers/<int:supplier_id>/rating-stats/', views.supplier_rating_stats_api, name='supplier_rating_stats_api'),
    path('api/rating-analytics/', views.supplier_rating_analytics_api, name='rating_analytics_api'),
    path('api/bulk-rate/', views.bulk_rate_suppliers, name='bulk_rate_api'),
    path('api/supplier-comparison/', views.supplier_comparison_api, name='supplier_comparison_api'),
    path('api/rating-suggestions/', views.rating_suggestions_api, name='rating_suggestions_api'),
    path('api/export-ratings/', views.export_ratings_csv_api, name='export_ratings_api'),

    # Export URLs
    path('export/suppliers/', views.export_suppliers_csv, name='export_suppliers'),
    path('export/purchase-orders/', views.export_purchase_orders_csv, name='export_purchase_orders'),
]