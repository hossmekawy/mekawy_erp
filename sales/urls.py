from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Standalone Page URLs
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('pos/', views.POSView.as_view(), name='pos_view'),

    # API URLs for the frontend
    path('api/products/', views.ProductListAPIView.as_view(), name='api_product_list'),
    path('api/customers/search/', views.CustomerSearchAPIView.as_view(), name='api_customer_search'),
    path('api/invoice/create/', views.CreateInvoiceAPIView.as_view(), name='api_invoice_create'),

    # Standard CRUD URLs for Invoices
    path('invoices/', views.SalesInvoiceListView.as_view(), name='invoice_list'),
    path('invoices/create/', views.SalesInvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', views.SalesInvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/update/', views.SalesInvoiceUpdateView.as_view(), name='invoice_update'),
    path('invoices/<int:pk>/delete/', views.SalesInvoiceDeleteView.as_view(), name='invoice_delete'),
    
    # New URL for generating PDF invoices
    path('invoices/<int:pk>/pdf/', views.GenerateInvoicePDF.as_view(), name='invoice_pdf'),
    path('prices/', views.ProductPriceListView.as_view(), name='product_price_list'),
    path('prices/update/', views.UpdateProductPriceAJAXView.as_view(), name='update_product_price_ajax'),
    path('prices/export/excel/', views.ExportPricesExcelView.as_view(), name='export_prices_excel'),
    path('prices/import/excel/', views.ImportPricesExcelView.as_view(), name='import_prices_excel'),
    path('prices/export/pdf/', views.ExportPricesPDFView.as_view(), name='export_prices_pdf'),

    # Price Lists
    path('pricelists/', views.PriceListView.as_view(), name='pricelist_list'),
    path('pricelists/create/', views.PriceListCreateView.as_view(), name='pricelist_create'),
]
