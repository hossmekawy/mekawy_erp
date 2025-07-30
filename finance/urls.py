# finance/urls.py

from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Account URLs
    path('accounts/', views.AccountListView.as_view(), name='account_list'),
    path('accounts/new/', views.AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/edit/', views.AccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', views.AccountDeleteView.as_view(), name='account_delete'),

    # Transaction URLs
    path('transactions/', views.TransactionListView.as_view(), name='transaction_list'),
    path('transactions/new/', views.TransactionCreateView.as_view(), name='transaction_create'),
    path('accounts/<int:pk>/statement/', views.AccountStatementView.as_view(), name='account_statement'),
path('transactions/<int:pk>/', views.TransactionDetailView.as_view(), name='transaction_detail'),
    
    # UPDATE THIS LINE to point to the new function view
    path('transactions/<int:pk>/pdf/', views.export_transaction_pdf, name='transaction_pdf'),

]