# finance/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Q, DecimalField, F
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import date, timedelta

from .models import Account, Transaction, AccountCategory, Invoice, Payment, Expense
from .forms import AccountForm, InvoiceForm, PaymentForm, ExpenseForm
from .utils import create_double_entry_transaction

# =============================================================================
# CORE FINANCIAL VIEWS
# =============================================================================

class FinanceDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'لوحة التحكم المالية'

        balances = AccountCategory.objects.values('category_type').annotate(
            total_debit=Coalesce(Sum('accounts__transaction_details__debit'), Decimal('0.0'), output_field=DecimalField()),
            total_credit=Coalesce(Sum('accounts__transaction_details__credit'), Decimal('0.0'), output_field=DecimalField())
        )

        kpis = {
            'total_assets': Decimal('0.0'), 'total_liabilities': Decimal('0.0'),
            'total_equity': Decimal('0.0'), 'total_revenues': Decimal('0.0'),
            'total_expenses': Decimal('0.0'),
        }

        for balance in balances:
            category_type = balance['category_type']
            debits = balance['total_debit']
            credits = balance['total_credit']
            
            total = debits - credits if category_type in ['asset', 'expense'] else credits - debits
            # Correctly map plural names
            kpis[f'total_{category_type}s'] = total
        
        kpis['net_worth'] = kpis['total_assets'] - kpis['total_liabilities']
        kpis['profit_loss'] = kpis['total_revenues'] - kpis['total_expenses']

        context['kpis'] = kpis
        context['recent_transactions'] = Transaction.objects.select_related('created_by').prefetch_related('details__account').order_by('-date', '-created_at')[:5]
        context['invoices_due'] = Invoice.objects.filter(status__in=['sent', 'partial', 'received']).order_by('due_date')[:5]
        
        return context

class JournalView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'finance/journal.html'
    context_object_name = 'transactions'
    paginate_by = 25

    def get_queryset(self):
        return Transaction.objects.prefetch_related('details__account').order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'دفتر اليومية العام'
        return context

class LedgerView(LoginRequiredMixin, DetailView):
    model = Account
    template_name = 'finance/ledger.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_object()
        context['page_title'] = f'دفتر أستاذ: {account.name}'
        
        details = account.transaction_details.select_related('transaction__created_by').order_by('transaction__date', 'transaction__created_at')
        
        running_balance = Decimal('0.0')
        ledger_entries = []
        
        for detail in details:
            change = (detail.debit - detail.credit) if account.category.category_type in ['asset', 'expense'] else (detail.credit - detail.debit)
            running_balance += change
            ledger_entries.append({'detail': detail, 'running_balance': running_balance})

        context['ledger_entries'] = ledger_entries
        context['final_balance'] = running_balance
        return context

# =============================================================================
# CHART OF ACCOUNTS CRUD
# =============================================================================

class ChartOfAccountsView(LoginRequiredMixin, ListView):
    model = AccountCategory
    template_name = 'finance/chart_of_accounts.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return AccountCategory.objects.prefetch_related('accounts').order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'دليل الحسابات'
        return context

class AccountCreateView(LoginRequiredMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:chart_of_accounts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'إنشاء حساب جديد'
        return context

    def form_valid(self, form):
        messages.success(self.request, f"تم إنشاء الحساب '{form.instance.name}' بنجاح.")
        return super().form_valid(form)

class AccountUpdateView(LoginRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'finance/account_form.html'
    success_url = reverse_lazy('finance:chart_of_accounts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'تعديل حساب: {self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f"تم تحديث الحساب '{form.instance.name}' بنجاح.")
        return super().form_valid(form)

class AccountDeleteView(LoginRequiredMixin, DeleteView):
    model = Account
    template_name = 'finance/confirm_delete.html'
    success_url = reverse_lazy('finance:chart_of_accounts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'حذف حساب: {self.object.name}'
        context['object_name'] = self.object.name
        return context

    def form_valid(self, form):
        messages.success(self.request, f"تم حذف الحساب '{self.object.name}' بنجاح.")
        return super().form_valid(form)

# =============================================================================
# INVOICE & BILL VIEWS
# =============================================================================

class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'finance/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        return Invoice.objects.select_related('recipient_content_type').prefetch_related('recipient').order_by('-issue_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'الفواتير والوصولات'
        return context

class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'finance/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'تفاصيل الفاتورة: {self.object.invoice_number}'
        context['payments'] = self.object.payments.all()
        return context

# =============================================================================
# PAYMENT VIEWS
# =============================================================================

class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'finance/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20

    def get_queryset(self):
        return Payment.objects.select_related('invoice', 'created_by', 'invoice__recipient').order_by('-payment_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'سجل المدفوعات'
        return context

class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'finance/payment_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = get_object_or_404(Invoice, pk=self.kwargs['invoice_pk'])
        context['invoice'] = invoice
        context['page_title'] = f'إضافة دفعة للفاتورة {invoice.invoice_number}'
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['invoice'] = get_object_or_404(Invoice, pk=self.kwargs['invoice_pk'])
        return kwargs

    def form_valid(self, form):
        invoice = get_object_or_404(Invoice, pk=self.kwargs['invoice_pk'])
        form.instance.invoice = invoice
        form.instance.created_by = self.request.user
        
        with transaction.atomic():
            payment = form.save()
            
            invoice.paid_amount = F('paid_amount') + payment.amount
            invoice.save()
            invoice.refresh_from_db()

            if invoice.balance_due <= 0:
                invoice.status = 'paid'
            else:
                invoice.status = 'partial'
            invoice.save(update_fields=['status'])

            # Corrected logic for paying a vendor bill
            cash_account = Account.objects.get(code='1010') # Cash/Bank account being paid from
            
            # Dynamically get the recipient's liability account
            recipient_account = Account.objects.filter(
                owner_content_type=invoice.recipient_content_type,
                owner_object_id=invoice.recipient_object_id
            ).first()

            if not recipient_account:
                messages.error(self.request, "لم يتم العثور على الحساب المالي للمستلم.")
                return self.form_invalid(form)

            create_double_entry_transaction(
                description=f"سداد دفعة للفاتورة {invoice.invoice_number}",
                created_by=self.request.user,
                debit_account=recipient_account, # Debit Accounts Payable (decreases liability)
                credit_account=cash_account, # Credit Cash/Bank (decreases asset)
                amount=payment.amount,
                date=payment.payment_date,
                source_document=payment
            )

        messages.success(self.request, f"تم تسجيل دفعة بقيمة {payment.amount} بنجاح.")
        return redirect('finance:invoice_detail', pk=invoice.pk)

# =============================================================================
# EXPENSE CRUD
# =============================================================================

class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = 'finance/expense_list.html'
    context_object_name = 'expenses'
    paginate_by = 20

    def get_queryset(self):
        return Expense.objects.select_related('expense_account', 'source_account', 'created_by').order_by('-expense_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'المصروفات'
        return context

class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'finance/expense_form.html'
    success_url = reverse_lazy('finance:expense_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'تسجيل مصروف جديد'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        with transaction.atomic():
            expense = form.save()
            create_double_entry_transaction(
                description=f"مصروف: {expense.description}",
                created_by=self.request.user,
                debit_account=expense.expense_account,
                credit_account=expense.source_account,
                amount=expense.amount,
                date=expense.expense_date,
                source_document=expense
            )
        
        messages.success(self.request, "تم تسجيل المصروف بنجاح.")
        return super().form_valid(form)

# =============================================================================
# FINANCIAL REPORTS
# =============================================================================

class IncomeStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/income_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'قائمة الدخل'

        # Date filtering
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        context['start_date'] = start_date
        context['end_date'] = end_date

        # Revenue
        revenues = Account.objects.filter(category__category_type='revenue')
        total_revenue = sum(acc.balance for acc in revenues)
        
        # Expenses
        expenses = Account.objects.filter(category__category_type='expense')
        total_expenses = sum(acc.balance for acc in expenses)
        
        # Net Income
        net_income = total_revenue - total_expenses

        context['revenues'] = revenues
        context['total_revenue'] = total_revenue
        context['expenses'] = expenses
        context['total_expenses'] = total_expenses
        context['net_income'] = net_income
        
        return context

class BalanceSheetView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/balance_sheet.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'الميزانية العمومية'
        context['report_date'] = date.today()

        # Assets
        asset_categories = AccountCategory.objects.filter(category_type='asset').prefetch_related('accounts')
        total_assets = sum(acc.balance for cat in asset_categories for acc in cat.accounts.all())

        # Liabilities
        liability_categories = AccountCategory.objects.filter(category_type='liability').prefetch_related('accounts')
        total_liabilities = sum(acc.balance for cat in liability_categories for acc in cat.accounts.all())

        # Equity
        equity_categories = AccountCategory.objects.filter(category_type='equity').prefetch_related('accounts')
        total_equity = sum(acc.balance for cat in equity_categories for acc in cat.accounts.all())

        context['asset_categories'] = asset_categories
        context['total_assets'] = total_assets
        context['liability_categories'] = liability_categories
        context['total_liabilities'] = total_liabilities
        context['equity_categories'] = equity_categories
        context['total_equity'] = total_equity
        context['total_liabilities_and_equity'] = total_liabilities + total_equity

        return context
