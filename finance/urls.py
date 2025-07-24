# finance/urls.py

from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Core Views
    path('', views.FinanceDashboardView.as_view(), name='dashboard'),
    path('journal/', views.JournalView.as_view(), name='journal'),
    path('ledger/<int:pk>/', views.LedgerView.as_view(), name='ledger'),

    # Chart of Accounts
    path('accounts/', views.ChartOfAccountsView.as_view(), name='chart_of_accounts'),
    path('accounts/create/', views.AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/update/', views.AccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', views.AccountDeleteView.as_view(), name='account_delete'),

    # Invoices & Bills
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),

    # Payments
    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('invoices/<int:invoice_pk>/add-payment/', views.PaymentCreateView.as_view(), name='payment_create'),

    # Expenses
    path('expenses/', views.ExpenseListView.as_view(), name='expense_list'),
    path('expenses/create/', views.ExpenseCreateView.as_view(), name='expense_create'),
    
    # Financial Reports
    path('reports/income-statement/', views.IncomeStatementView.as_view(), name='income_statement'),
    path('reports/balance-sheet/', views.BalanceSheetView.as_view(), name='balance_sheet'),
]
