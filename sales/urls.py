from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('invoices/', views.SalesInvoiceListView.as_view(), name='invoice_list'),
    path('invoices/create/', views.SalesInvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', views.SalesInvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/update/', views.SalesInvoiceUpdateView.as_view(), name='invoice_update'),

    path('pricelists/', views.PriceListView.as_view(), name='pricelist_list'),
    path('pricelists/create/', views.PriceListCreateView.as_view(), name='pricelist_create'),
    
    # --- NEW API URL for Customer Search ---
    path('api/customers/search/', views.CustomerSearchAPIView.as_view(), name='api_customer_search'),
]
