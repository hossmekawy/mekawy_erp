# finance/urls.py

from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # --- NEW: Manufacturer Finance URLs ---
    path('manufacturers/', views.ManufacturerStatementListView.as_view(), name='manufacturer_statement_list'),
    path('manufacturers/<int:pk>/statement/', views.ManufacturerStatementDetailView.as_view(), name='manufacturer_statement_detail'),
    path('manufacturers/<int:pk>/pay/', views.CreateManufacturerPaymentView.as_view(), name='manufacturer_payment_create'),
    path('manufacturers/<int:pk>/recalculate/', views.recalculate_and_create_transactions, name='manufacturer_recalculate'),
    path('manufacturers/<int:pk>/statement/pdf/', views.PrintManufacturerStatementView.as_view(), name='manufacturer_statement_pdf'),


    # Existing Account URLs
    path('accounts/', views.AccountListView.as_view(), name='account_list'),
    path('accounts/new/', views.AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/edit/', views.AccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', views.AccountDeleteView.as_view(), name='account_delete'),
    path('accounts/<int:pk>/statement/', views.AccountStatementView.as_view(), name='account_statement'),

    # Existing Transaction URLs
    path('transactions/', views.TransactionListView.as_view(), name='transaction_list'),
    path('transactions/new/', views.TransactionCreateView.as_view(), name='transaction_create'),
    path('transactions/<int:pk>/', views.TransactionDetailView.as_view(), name='transaction_detail'),
    path('transactions/<int:pk>/pdf/', views.export_transaction_pdf, name='transaction_pdf'),
]
