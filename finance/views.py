# Django Core Imports
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction as db_transaction
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings

# Python Standard Library Imports
from decimal import Decimal
from datetime import datetime

# Third-Party Imports
import pdfkit

# Local App Imports
from .models import Account, Transaction
from .forms import AccountForm, TransactionForm


# =================================================================
# Account Views (CRUD and Statement)
# =================================================================

class AccountListView(ListView):
    """Displays a list of all financial accounts."""
    model = Account
    template_name = 'finance/account_list.html'
    context_object_name = 'accounts'

class AccountCreateView(SuccessMessageMixin, CreateView):
    """View to create a new financial account."""
    model = Account
    form_class = AccountForm
    template_name = 'finance/account_form.html'
    success_message = "تم إنشاء الحساب بنجاح!"
    success_url = reverse_lazy('finance:account_list')

class AccountUpdateView(SuccessMessageMixin, UpdateView):
    """View to update an existing financial account."""
    model = Account
    form_class = AccountForm
    template_name = 'finance/account_form.html'
    success_message = "تم تحديث الحساب بنجاح!"
    success_url = reverse_lazy('finance:account_list')

class AccountDeleteView(SuccessMessageMixin, DeleteView):
    """View to delete a financial account with confirmation."""
    model = Account
    template_name = 'finance/confirm_delete.html'
    success_url = reverse_lazy('finance:account_list')
    success_message = "تم حذف الحساب بنجاح."
    
    def post(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().post(request, *args, **kwargs)

class AccountStatementView(View):
    """Generates and displays a detailed account statement with a running balance."""
    template_name = 'finance/account_statement.html'

    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk)
        
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        transactions = Transaction.objects.filter(
            Q(account=account) | Q(to_account=account)
        ).order_by('timestamp')

        opening_balance = Decimal('0.00')
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            transactions_before = transactions.filter(timestamp__date__lt=start_date)
            
            for trans in transactions_before:
                if trans.account == account:
                    if trans.type in ['WITHDRAWAL', 'TRANSFER']:
                        opening_balance -= trans.amount
                    elif trans.type == 'DEPOSIT':
                        opening_balance += trans.amount
                elif trans.to_account == account:
                    opening_balance += trans.amount
            
            transactions = transactions.filter(timestamp__date__gte=start_date)

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            transactions = transactions.filter(timestamp__date__lte=end_date)
            
        transactions_with_balance = []
        running_balance = opening_balance
        
        for trans in transactions:
            debit = Decimal('0.00')
            credit = Decimal('0.00')

            if trans.account == account and trans.type in ['WITHDRAWAL', 'TRANSFER']:
                running_balance -= trans.amount
                debit = trans.amount
            elif (trans.to_account == account and trans.type == 'TRANSFER') or \
                 (trans.account == account and trans.type == 'DEPOSIT'):
                running_balance += trans.amount
                credit = trans.amount

            transactions_with_balance.append({
                'transaction': trans,
                'debit': debit,
                'credit': credit,
                'running_balance': running_balance
            })

        context = {
            'account': account,
            'transactions_with_balance': transactions_with_balance,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
        }
        return render(request, self.template_name, context)

# =================================================================
# Transaction Views (CRUD and PDF Export)
# =================================================================

class TransactionListView(ListView):
    """Displays a paginated list of all transactions with search functionality."""
    model = Transaction
    template_name = 'finance/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related('account', 'to_account')
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query) |
                Q(reference__icontains=search_query) |
                Q(account__name__icontains=search_query) |
                Q(to_account__name__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['per_page'] = self.request.GET.get('per_page', self.paginate_by)
        return context

class TransactionCreateView(SuccessMessageMixin, CreateView):
    """View to create a new financial transaction."""
    model = Transaction
    form_class = TransactionForm
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')
    success_message = "تم تسجيل الحركة المالية بنجاح!"

    @db_transaction.atomic
    def form_valid(self, form):
        form.save()
        return super().form_valid(form)
    
class TransactionDetailView(DetailView):
    """Displays the details of a single transaction."""
    model = Transaction
    template_name = 'finance/transaction_detail.html'
    context_object_name = 'transaction'

@login_required
def export_transaction_pdf(request, pk):
    """Exports a single Transaction to a PDF file using pdfkit."""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    html = render_to_string('pdf/finance/transaction_invoice.html', {'transaction': transaction})
    
    options = {
        'page-size': 'A5',
        'margin-top': '0.5in',
        'margin-right': '0.5in',
        'margin-bottom': '0.5in',
        'margin-left': '0.5in',
        'encoding': "UTF-8",
        '--load-error-handling': 'ignore',
    }

    try:
        config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Transaction_{transaction.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {e}", status=500)