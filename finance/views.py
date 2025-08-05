# finance/views.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Django Core Imports
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import FormView
from django.contrib.contenttypes.models import ContentType
from production.models import AssemblyProcess, DyeingProcess, FinishingProcess, ManufacturerProductPrice
from django.db import transaction as db_transaction
from django.utils.translation import gettext_lazy as _

# Python Standard Library Imports
from decimal import Decimal
from datetime import datetime

# Third-Party Imports
import pdfkit

# Local App Imports
from .models import Account, Transaction
from .forms import AccountForm, TransactionForm, ManufacturerPaymentForm # Import new form
from production.models import ExternalManufacturer


# =================================================================
# Manufacturer Finance Views
# =================================================================

def create_invoice_and_transaction(request, process_instance, manufacturer, cost, expense_name, notes):
    """
    Helper function to create a financial transaction for a production process.
    """
    try:
        manufacturer_liability_account = Account.objects.get(
            manufacturer=manufacturer,
            account_type='LIABILITY'
        )
        with db_transaction.atomic():
            # This logic is now handled by the recalculate_and_create_transactions view
            # to prevent balance errors during recalculation.
            # manufacturer_liability_account.balance += cost
            # manufacturer_liability_account.save()

            Transaction.objects.create(
                account=manufacturer_liability_account,
                type='MANUFACTURING_DEBT',
                amount=cost,
                description=notes,
                reference=f"{type(process_instance).__name__}-{process_instance.id}",
                content_object=process_instance,
            )
        return True
    except Account.DoesNotExist:
        messages.error(request, f"CRITICAL ERROR: Financial account for manufacturer '{manufacturer.name}' not found.")
        return False
    except Exception as e:
        messages.error(request, f"An unexpected error occurred while creating financial records: {e}")
        return False


class ManufacturerStatementListView(LoginRequiredMixin, ListView):
    """
    Displays a list of all external manufacturers and their financial balances.
    """
    model = ExternalManufacturer
    template_name = 'finance/manufacturer_list.html'
    context_object_name = 'manufacturers'
    
    def get_queryset(self):
        # We fetch manufacturers and annotate their account balance
        return ExternalManufacturer.objects.select_related('finance_account').all()


class ManufacturerStatementDetailView(LoginRequiredMixin, View):
    """
    Generates and displays a detailed statement for a specific manufacturer,
    showing a breakdown of each production job and payment.
    """
    template_name = 'finance/manufacturer_statement_detail.html'

    def get(self, request, pk):
        manufacturer = get_object_or_404(ExternalManufacturer.objects.select_related('finance_account'), pk=pk)
        
        if not manufacturer.finance_account:
            messages.error(request, "This manufacturer does not have a financial account linked.")
            return redirect('finance:manufacturer_statement_list')

        account = manufacturer.finance_account
        
        # Get all transactions for the account, prefetching related source objects
        # This is a key optimization to prevent many database queries.
        transactions_qs = Transaction.objects.filter(account=account).order_by('timestamp').prefetch_related('content_object')
        
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        opening_balance = Decimal('0.00')
        
        # FIX: The opening balance calculation is now correctly placed inside the
        # date filter check to ensure 'start_date' exists before it's used.
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                
                # Calculate opening balance
                opening_debit = Transaction.objects.filter(
                    account=account, timestamp__date__lt=start_date, type='MANUFACTURING_DEBT'
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                
                opening_credit = Transaction.objects.filter(
                    account=account, timestamp__date__lt=start_date, type='MANUFACTURER_PAYMENT'
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

                opening_balance = opening_debit - opening_credit
                
                # Filter the main queryset for the selected date range
                transactions_qs = transactions_qs.filter(timestamp__date__gte=start_date)
            except (ValueError, TypeError):
                messages.error(request, "Invalid start date format. Please use YYYY-MM-DD.")
                start_date_str = None # Reset if invalid

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                transactions_qs = transactions_qs.filter(timestamp__date__lte=end_date)
            except (ValueError, TypeError):
                messages.error(request, "Invalid end date format. Please use YYYY-MM-DD.")
                end_date_str = None # Reset if invalid

        statement_items = []
        running_balance = opening_balance
        
        for trans in transactions_qs:
            item = {
                'is_payment': False,
                'date': trans.timestamp,
                'order_code': '--', 'product_name': '--', 'qty_sent': '--',
                'qty_received': '--', 'defects': '--', 'lost': '--',
                'price': Decimal('0.00'), 'debit': Decimal('0.00'), 'credit': Decimal('0.00'),
                'notes': trans.description,
            }

            if trans.type == 'MANUFACTURING_DEBT':
                # This is a charge from a production process
                process = trans.content_object
                if process:
                    # Safely get production order details, works for Assembly, Dyeing, Finishing
                    production_order = getattr(process, 'production_order', getattr(getattr(process, 'assembly_process', None), 'production_order', None))
                    if production_order:
                        item['order_code'] = production_order.order_number
                        item['product_name'] = production_order.product.name

                    # Get process-specific quantities
                    qty_sent = getattr(process, 'quantity_sent', getattr(process, 'quantity_input', 0))
                    qty_received = getattr(process, 'quantity_received', getattr(process, 'quantity_output', 0))
                    defects = getattr(process, 'defects_count', getattr(process, 'defects_in_finishing', 0))
                    
                    item.update({
                        'qty_sent': qty_sent,
                        'qty_received': qty_received,
                        'defects': defects,
                        'lost': (qty_sent or 0) - (qty_received or 0) - (defects or 0)
                    })
                    
                    effective_qty = qty_received or 0
                    if effective_qty > 0:
                        item['price'] = trans.amount / effective_qty
                
                item['debit'] = trans.amount
                running_balance += trans.amount

            elif trans.type == 'MANUFACTURER_PAYMENT':
                # This is a payment we made to them
                item['is_payment'] = True
                item['credit'] = trans.amount
                running_balance -= trans.amount
            
            item['balance'] = running_balance
            statement_items.append(item)

        context = {
            'manufacturer': manufacturer,
            'account': account,
            'statement_items': statement_items,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
        }
        return render(request, self.template_name, context)


class CreateManufacturerPaymentView(LoginRequiredMixin, SuccessMessageMixin, FormView):
    """
    A view for creating a payment to a manufacturer.
    Uses FormView because it performs custom logic, not a simple model creation.
    """
    form_class = ManufacturerPaymentForm
    template_name = 'finance/manufacturer_payment_form.html'
    success_message = "تم تسجيل الدفعة للمصنع بنجاح!"

    def get_form_kwargs(self):
        """Passes the manufacturer instance to the form's __init__ method."""
        kwargs = super().get_form_kwargs()
        self.manufacturer = get_object_or_404(ExternalManufacturer, pk=self.kwargs['pk'])
        kwargs['manufacturer'] = self.manufacturer
        return kwargs

    def form_valid(self, form):
        """If the form is valid, save the transaction and show a success message."""
        form.save()
        # Success message is handled by SuccessMessageMixin
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Adds the manufacturer to the template context."""
        context = super().get_context_data(**kwargs)
        # Ensure manufacturer is available in context even on initial GET
        if not hasattr(self, 'manufacturer'):
            self.manufacturer = get_object_or_404(ExternalManufacturer, pk=self.kwargs['pk'])
        context['manufacturer'] = self.manufacturer
        return context

    def get_success_url(self):
        """Redirects back to the manufacturer's statement page after success."""
        return reverse('finance:manufacturer_statement_detail', kwargs={'pk': self.kwargs['pk']})



# ... (rest of your existing views: AccountListView, TransactionListView, etc.)
# The existing views should remain unchanged.
# I'm adding the new views and leaving the old ones as they are.

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
                    if trans.type in ['WITHDRAWAL', 'TRANSFER', 'MANUFACTURER_PAYMENT']:
                        opening_balance -= trans.amount
                    elif trans.type in ['DEPOSIT', 'MANUFACTURING_DEBT']:
                        opening_balance += trans.amount
                elif trans.to_account == account:
                    opening_balance += trans.amount
            
            transactions = transactions.filter(timestamp__date__gte=start_date)

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            transactions = transactions.filter(timestamp__date__lte=end_date)
            
        transactions_with_balance = []
        running_balance = opening_balance
        
        # =====================================================================
        # ===== FIX STARTS HERE ===============================================
        # =====================================================================
        
        # Replace the old loop logic with this clear and correct structure.
        for trans in transactions:
            debit = Decimal('0.00')
            credit = Decimal('0.00')

            # Case 1: The current account is the primary/source account
            if trans.account == account:
                if trans.type in ['WITHDRAWAL', 'TRANSFER', 'MANUFACTURER_PAYMENT']:
                    # These are debits (money going out)
                    running_balance -= trans.amount
                    debit = trans.amount
                elif trans.type in ['DEPOSIT', 'MANUFACTURING_DEBT']:
                    # These are credits (money coming in or liability increasing)
                    running_balance += trans.amount
                    credit = trans.amount
            
            # Case 2: The current account is the destination of a transfer
            elif trans.to_account == account:
                # This is always a credit (money coming in)
                running_balance += trans.amount
                credit = trans.amount

            transactions_with_balance.append({
                'transaction': trans,
                'debit': debit,
                'credit': credit,
                'running_balance': running_balance
            })

        # ===================================================================
        # ===== FIX ENDS HERE ===============================================
        # ===================================================================

        context = {
            'account': account,
            'transactions_with_balance': transactions_with_balance,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
        }
        return render(request, self.template_name, context)

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

# THIS IS CORRECT - IT SAVES ONLY ONCE
class TransactionCreateView(SuccessMessageMixin, CreateView):
    """View to create a new financial transaction."""
    model = Transaction
    form_class = TransactionForm
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_list')
    success_message = "تم تسجيل الحركة المالية بنجاح!"

    # By removing the custom form_valid method, the parent CreateView
    # will handle saving the form correctly, exactly one time.
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
        # Make sure you have WKHTMLTOPDF_PATH configured in your settings.py
        config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Transaction_{transaction.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {e}", status=500)

@login_required
@require_POST
def recalculate_and_create_transactions(request, pk):
    """
    FIX: This function is now completely rewritten to be more robust.
    It finds all completed jobs, checks for existing transactions (including duplicates),
    calculates the correct cost, and then creates or updates the single correct transaction.
    Finally, it recalculates the manufacturer's total balance.
    """
    manufacturer = get_object_or_404(ExternalManufacturer, pk=pk)
    account = manufacturer.finance_account
    if not account:
        messages.error(request, "This manufacturer does not have a financial account.")
        return redirect('finance:manufacturer_statement_detail', pk=manufacturer.pk)

    processes_to_check = []
    processes_to_check.extend(AssemblyProcess.objects.filter(external_manufacturer=manufacturer, is_completed=True))
    processes_to_check.extend(DyeingProcess.objects.filter(dyeing_facility=manufacturer, is_completed=True))
    processes_to_check.extend(FinishingProcess.objects.filter(external_manufacturer=manufacturer, is_completed=True))

    updated_count = 0
    created_count = 0
    errors_found = 0
    duplicates_cleaned = 0

    with db_transaction.atomic():
        for process in processes_to_check:
            production_order = None
            try:
                production_order = getattr(process, 'production_order', 
                                   getattr(getattr(process, 'assembly_process', None), 'production_order', 
                                   getattr(getattr(getattr(process, 'dyeing_process', None), 'assembly_process', None), 'production_order', None)))
                if not production_order:
                    continue

                price_record = ManufacturerProductPrice.objects.get(
                    manufacturer=manufacturer,
                    product=production_order.product
                )
                
                qty = getattr(process, 'quantity_received', getattr(process, 'quantity_output', 0))
                cost = price_record.price * qty

                # Update cost on the process model itself for record-keeping
                if isinstance(process, AssemblyProcess): process.assembly_cost = cost
                elif isinstance(process, DyeingProcess): process.total_dyeing_cost = cost
                elif isinstance(process, FinishingProcess): process.total_finishing_cost = cost
                process.save()

                content_type = ContentType.objects.get_for_model(process)
                
                all_related_transactions = Transaction.objects.filter(content_type=content_type, object_id=process.id)
                
                master_transaction = all_related_transactions.first()
                if all_related_transactions.count() > 1:
                    transactions_to_delete = all_related_transactions.exclude(pk=master_transaction.pk)
                    duplicates_cleaned += transactions_to_delete.count()
                    transactions_to_delete.delete()

                if cost > 0:
                    if master_transaction:
                        master_transaction.amount = cost
                        master_transaction.description = _("تكلفة: {prod_name} (مُعاد حسابها)").format(prod_name=production_order.product.name)
                        master_transaction.save()
                        updated_count += 1
                    else:
                        success = create_invoice_and_transaction(
                            request=request, process_instance=process, manufacturer=manufacturer,
                            cost=cost, expense_name="Outsourced Cost (Recalculated)",
                            notes=_("تكلفة: {prod_name}").format(prod_name=production_order.product.name)
                        )
                        if success:
                            created_count += 1
                        else:
                            errors_found += 1
                        
            except ManufacturerProductPrice.DoesNotExist:
                order_num = production_order.order_number if production_order else "Unknown"
                messages.warning(request, f"Could not process order '{order_num}': Price not set.")
                errors_found += 1
            except Exception as e:
                order_num = production_order.order_number if production_order else "Unknown"
                messages.error(request, f"An error occurred for order '{order_num}': {e}")
                errors_found += 1
        
        # After processing all jobs, recalculate the final balance for accuracy
        total_debit = Transaction.objects.filter(account=account, type='MANUFACTURING_DEBT').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_credit = Transaction.objects.filter(account=account, type='MANUFACTURER_PAYMENT').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        account.balance = total_debit - total_credit
        account.save()

    if created_count > 0:
        messages.success(request, f"Successfully created {created_count} missing financial transactions.")
    if updated_count > 0:
        messages.success(request, f"Successfully updated {updated_count} existing transactions.")
    if duplicates_cleaned > 0:
        messages.info(request, f"Cleaned up {duplicates_cleaned} duplicate transactions.")
    if errors_found == 0 and created_count == 0 and updated_count == 0:
        messages.info(request, "No transactions needed to be created or updated.")
        
    return redirect('finance:manufacturer_statement_detail', pk=manufacturer.pk)
