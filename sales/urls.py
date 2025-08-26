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
]
