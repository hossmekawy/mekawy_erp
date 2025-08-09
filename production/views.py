from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from finance.models import Account, Transaction # Make sure your finance app is named 'finance'
from xhtml2pdf import pisa
import io
from datetime import datetime, timedelta
import logging
import pdfkit
import openpyxl
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
import logging  # FIX: This was incorrectly 'import logger'
from itertools import chain
from operator import attrgetter
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.utils.translation import gettext_lazy as _

from django.views.decorators.http import require_POST
from django.urls import NoReverseMatch, reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Avg, Count, F
from django.db import models

from django.utils import timezone
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.conf import settings
from django.forms import inlineformset_factory
from django.db import transaction
from django.db.models import Max
from datetime import datetime, timedelta, date
from decimal import Decimal
import logging
import pdfkit
import csv
import json
from django.views import View
from collections import Counter
from django.db.models.functions import TruncMonth

from .models import (
    ManufacturerProductPrice, ProductionOrder, CuttingProcess, AssemblyProcess, DyeingProcess, 
    FinishingProcess, ExternalManufacturer, ExitPermit, ReceiptConfirmation, 
    ProductionCostAnalysis, BillOfMaterials, BOMItem, CutPiece, CuttingTable, 
    AssemblyComponent, GarmentDraw, FinishingComponent, QualityControlCheck,ProductionReport
)
from .forms import (
    CutPieceFormSet, CuttingTableForm, ProductionOrderForm, BillOfMaterialsForm, BOMItemFormSet, CuttingProcessForm, 
    AssemblyProcessForm, DyeingProcessForm, FinishingProcessForm, FinishingReceiveForm,
    AssemblyReceiveForm, DyeingReceiveForm, ExternalManufacturerForm, ExitPermitForm,
    ReceiptConfirmationForm, QualityControlCheckForm, ProductionCostAnalysisUpdateForm,SendAdditionalComponentFormSet,
    AssemblySendForm, DyeingSendForm, FinishingSendForm ,CuttingTableFormSet,CustomAssemblyComponentFormSet,ManufacturerProductPriceFormSet ,ExternalManufacturerForm, CustomFinishingComponentFormSet  
)
from warehouses.models import Product, StockItem, StockMovement, ProductBatch, Category , Warehouse


import qrcode
import base64
from io import BytesIO

User = get_user_model()
logger = logging.getLogger(__name__)


def create_invoice_and_transaction(request, process_instance, manufacturer, cost, expense_name, notes):
    """
    Helper function to create a financial transaction for a production process.
    This function creates a debt transaction against the manufacturer's account.
    """
    try:
        # 1. Find the manufacturer's liability account (created by a signal or manually)
        manufacturer_liability_account = Account.objects.get(
            manufacturer=manufacturer,
            account_type='LIABILITY'
        )

        # 2. Create the MANUFACTURING_DEBT transaction within a single database operation
        with transaction.atomic():
            # This transaction increases the liability account (what we owe them)
            manufacturer_liability_account.balance += cost
            manufacturer_liability_account.save()

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
        messages.error(request, f"CRITICAL ERROR: Financial account for manufacturer '{manufacturer.name}' not found. The transaction could not be recorded.")
        return False
    except Exception as e:
        logger.error(f"Error creating financial transaction for {manufacturer.name}: {e}")
        messages.error(request, f"An unexpected error occurred while creating financial records: {e}")
        return False


@login_required
@require_POST
def create_manufacturer_account_view(request, pk):
    """
    Creates a financial account for an existing external manufacturer.
    """
    manufacturer = get_object_or_404(ExternalManufacturer, pk=pk)
    
    if hasattr(manufacturer, 'finance_account') and manufacturer.finance_account is not None:
        messages.warning(request, f"The financial account for '{manufacturer.name}' already exists.")
    else:
        try:
            Account.objects.create(
                name=f"Factory Account: {manufacturer.name}",
                account_type='LIABILITY',
                manufacturer=manufacturer
            )
            messages.success(request, f"Financial account for '{manufacturer.name}' was created successfully.")
        except Exception as e:
            messages.error(request, f"An error occurred while creating the account: {e}")
            
    return redirect('production:manufacturers:manufacturer_detail', pk=manufacturer.pk)

# Dashboard View
# Dashboard View (update the get_context_data method)
class ProductionDashboardView(LoginRequiredMixin, TemplateView):
    """
    Handles the display of the main production dashboard, including various statistics
    and charts related to production orders and processes.
    """
    template_name = 'production/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # --- Date range for display and filtering ---
        end_date_str = self.request.GET.get('date_to')
        start_date_str = self.request.GET.get('date_from')

        try:
            context['date_to'] = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()
            context['date_from'] = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else context['date_to'] - timedelta(days=29)
        except (ValueError, TypeError):
            context['date_to'] = timezone.now().date()
            context['date_from'] = context['date_to'] - timedelta(days=29)

        # General order stats within the selected date range
        orders_in_range = ProductionOrder.objects.filter(created_at__date__range=[context['date_from'], context['date_to']])
        context['total_orders'] = orders_in_range.count()
        context['active_orders'] = ProductionOrder.objects.filter(
            status__in=['approved', 'in_cutting', 'in_assembly', 'in_dyeing', 'in_finishing']
        ).count()
        context['completed_orders'] = ProductionOrder.objects.filter(status='completed').count()
        context['pending_orders'] = ProductionOrder.objects.filter(status='draft').count()
        
        # Recent orders for the table display
        context['recent_orders'] = ProductionOrder.objects.select_related(
            'product', 'created_by'
        ).order_by('-created_at')[:10]
        
        # Active processes count
        context['active_cutting'] = CuttingProcess.objects.filter(is_completed=False).count()
        context['active_assembly'] = AssemblyProcess.objects.filter(is_completed=False).count()
        context['active_dyeing'] = DyeingProcess.objects.filter(is_completed=False).count()
        context['active_finishing'] = FinishingProcess.objects.filter(is_completed=False).count()
        
        # Alerts
        context['low_textile_stock'] = StockItem.objects.filter(
            product__product_type='fabric',
            quantity__lt=F('product__min_stock_level')
        ).count()
        context['pending_exit_permits'] = ExitPermit.objects.filter(status='pending').count()
        context['pending_quality_checks'] = QualityControlCheck.objects.filter(approved=False).count()
        
        # Monthly stats
        current_month = timezone.now().replace(day=1)
        context['monthly_stats'] = {
            'orders_created': ProductionOrder.objects.filter(created_at__gte=current_month).count(),
            'orders_completed': ProductionOrder.objects.filter(
                status='completed', 
                actual_completion_date__gte=current_month.date()
            ).count(),
            'total_pieces_produced': ProductionOrder.objects.filter(
                status='completed',
                actual_completion_date__gte=current_month.date()
            ).aggregate(total=Sum('quantity_ordered'))['total'] or 0,
        }
        
        # Monthly trend data for charts
        context['monthly_trend_data'] = self.get_monthly_trend_data()
        
        # --- Trousers Production Stats ---
        today = timezone.now().date()
        # This query assumes trousers are identified by the product name.
        # Adjust if you use categories or another method.
        base_trousers_query = ProductionOrder.objects.filter(
            status='completed',
            product__name__icontains='بنطلون' 
        )

        def get_production_sum(query, start_date):
            """Helper function to aggregate production quantity from a start date."""
            return query.filter(actual_completion_date__gte=start_date).aggregate(
                total=Coalesce(Sum('quantity_ordered'), 0)
            )['total']

        context['trousers_produced'] = {
            'last_day': get_production_sum(base_trousers_query, today - timedelta(days=1)),
            'last_week': get_production_sum(base_trousers_query, today - timedelta(weeks=1)),
            'last_month': get_production_sum(base_trousers_query, today - timedelta(days=30)),
            'last_3_months': get_production_sum(base_trousers_query, today - timedelta(days=90)),
            'last_6_months': get_production_sum(base_trousers_query, today - timedelta(days=180)),
            'last_year': get_production_sum(base_trousers_query, today - timedelta(days=365)),
        }
        
        return context

    def get_monthly_trend_data(self):
        """Get monthly trend data for the last 6 months"""
        end_date = timezone.now().date()
        # Go back 5 full months from the start of the current month to get 6 months total
        start_date = (end_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(4):
            start_date = (start_date - timedelta(days=1)).replace(day=1)

        monthly_orders = ProductionOrder.objects.filter(
            created_at__date__gte=start_date
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            orders_created=Count('id'),
            orders_completed=Count('id', filter=Q(status='completed')),
        ).order_by('month')
        
        # Prepare data for the chart
        months = []
        orders_created_data = []
        orders_completed_data = []
        
        month_iterator = start_date
        while month_iterator <= end_date:
            months.append(month_iterator.strftime('%B %Y'))
            month_data = next((item for item in monthly_orders if item['month'].date() == month_iterator), None)
            
            if month_data:
                orders_created_data.append(month_data['orders_created'])
                orders_completed_data.append(month_data['orders_completed'])
            else:
                orders_created_data.append(0)
                orders_completed_data.append(0)
            
            # Move to the next month
            next_month = month_iterator.replace(day=28) + timedelta(days=4)
            month_iterator = next_month.replace(day=1)
        
        month_names_ar = {
            'January': 'يناير', 'February': 'فبراير', 'March': 'مارس', 'April': 'أبريل',
            'May': 'مايو', 'June': 'يونيو', 'July': 'يوليو', 'August': 'أغسطس',
            'September': 'سبتمبر', 'October': 'أكتوبر', 'November': 'نوفمبر', 'December': 'ديسمبر'
        }
        
        months_ar = [f"{month_names_ar.get(m.split(' ')[0], m.split(' ')[0])} {m.split(' ')[1]}" for m in months]
        
        return {
            'months': months_ar,
            'orders_created': orders_created_data,
            'orders_completed': orders_completed_data,
        }


class ExportProductionReportView(LoginRequiredMixin, View):
    
    def get_queryset(self, report_type):
        today = timezone.now().date()
        queryset = ProductionOrder.objects.filter(status='completed').select_related('product', 'created_by')
        title = "تقرير الإنتاج العام"
        time_filters = {
            'day': timedelta(days=1), 'week': timedelta(weeks=1), 'month': timedelta(days=30),
            '3_months': timedelta(days=90), '6_months': timedelta(days=180), 'year': timedelta(days=365),
        }
        if 'trousers' in report_type:
            queryset = queryset.filter(product__name__icontains='بنطلون')
            title = "تقرير إنتاج البناطيل"
            for key, delta in time_filters.items():
                if f'last_{key}' in report_type:
                    queryset = queryset.filter(actual_completion_date__gte=(today - delta))
                    title += f" - آخر {key.replace('_', ' ')}"
                    break
        return queryset, title

    def render_to_pdf(self, template_path, context):
        """Renders a given Django template to a PDF response using wkhtmltopdf."""
        html_string = render_to_string(template_path, context)
        try:
            pdf_options = {
                'encoding': "UTF-8",
                'page-size': 'A5',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
            }
            
            # FIX: Check if the setting exists. If it does, create a config object.
            if hasattr(settings, 'WKHTMLTOPDF_PATH') and settings.WKHTMLTOPDF_PATH:
                config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
                pdf = pdfkit.from_string(html_string, False, configuration=config, options=pdf_options)
            else:
                # If the setting doesn't exist, let pdfkit try to find the executable in the system PATH.
                pdf = pdfkit.from_string(html_string, False, options=pdf_options)

            response = HttpResponse(pdf, content_type='application/pdf')
            return response
        except OSError as e:
            # This error is often raised if wkhtmltopdf is not found at all.
            logger.error(f"PDF generation failed: {e}. Is wkhtmltopdf installed and in your PATH?")
            error_message = (
                "Error generating PDF: Could not find wkhtmltopdf executable. "
                "Please ensure it is installed and accessible in your system's PATH, "
                "or define the WKHTMLTOPDF_PATH in your Django settings.py file."
            )
            return HttpResponse(error_message, status=500)
        except Exception as e:
            # Catch any other unexpected errors.
            logger.error(f"PDF generation failed with an unexpected error: {e}")
            return HttpResponse(f"An unexpected error occurred during PDF generation: {e}", status=500)

    def render_to_excel(self, queryset, title):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Production Report"
        sheet.sheet_view.rightToLeft = True
        header_font = Font(bold=True, size=14, name='Arial')
        title_font = Font(bold=True, size=18, name='Arial')
        cell_font = Font(size=12, name='Arial')
        center_align = Alignment(horizontal='center', vertical='center')
        sheet.merge_cells('A1:E1')
        title_cell = sheet['A1']
        title_cell.value = title
        title_cell.font = title_font
        title_cell.alignment = center_align
        headers = ['رقم الأمر', 'اسم المنتج', 'الكمية', 'تاريخ الإكمال', 'تم إنشاؤه بواسطة']
        for col_num, header_title in enumerate(headers, 1):
            cell = sheet.cell(row=3, column=col_num)
            cell.value = header_title
            cell.font = header_font
            cell.alignment = center_align
            sheet.column_dimensions[get_column_letter(col_num)].width = 25
        for row_num, order in enumerate(queryset, 4):
            sheet.cell(row=row_num, column=1, value=order.order_number).font = cell_font
            sheet.cell(row=row_num, column=2, value=order.product.name).font = cell_font
            sheet.cell(row=row_num, column=3, value=order.quantity_ordered).font = cell_font
            sheet.cell(row=row_num, column=4, value=order.actual_completion_date.strftime('%Y-%m-%d')).font = cell_font
            sheet.cell(row=row_num, column=5, value=order.created_by.username if order.created_by else 'N/A').font = cell_font
        workbook.save(response)
        return response

    def get(self, request, *args, **kwargs):
        report_type = request.GET.get('report_type', 'all_completed')
        export_format = request.GET.get('format', 'pdf')
        queryset, title = self.get_queryset(report_type)
        today = timezone.now().date()

        file_extension = 'xlsx' if export_format == 'excel' else export_format
        filename = f"production_report_{report_type}_{today}.{file_extension}"

        if export_format == 'pdf':
            context = {'orders': queryset, 'title': title}
            response = self.render_to_pdf('pdf/production/production_report_pdf.html', context)
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        elif export_format == 'excel':
            response = self.render_to_excel(queryset, title)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            messages.error(request, "تنسيق التصدير غير صالح.")
            return redirect('production:dashboard')


# Production Order Views
class ProductionOrderListView(LoginRequiredMixin, ListView):
    model = ProductionOrder
    template_name = 'production/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20
    
    def get_queryset(self):
        # Combines the original select_related with the new prefetch_related for efficiency
        queryset = ProductionOrder.objects.select_related(
            'product', 'product__category', 'textile_stock__product', 
            'created_by', 'cutting_process__cutter'
        ).prefetch_related(
            'assembly_processes__assembler', 
            'assembly_processes__external_manufacturer',
            'assembly_processes__dyeing_processes__dyeing_facility',
            'assembly_processes__dyeing_processes__finishing_process__finisher',
            'assembly_processes__dyeing_processes__finishing_process__external_manufacturer'
        ).order_by('-created_at')
        
        # --- All of your original filtering logic is preserved ---
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(batch_number__icontains=search) |
                Q(product__name__icontains=search)
            )
        
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        priority_filter = self.request.GET.get('priority')
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        created_by = self.request.GET.get('created_by')
        if created_by:
            queryset = queryset.filter(created_by_id=created_by)
        
        product_category = self.request.GET.get('product_category')
        if product_category:
            queryset = queryset.filter(product__category_id=product_category)
        
        quantity_min = self.request.GET.get('quantity_min')
        if quantity_min:
            queryset = queryset.filter(quantity_ordered__gte=quantity_min)
        
        quantity_max = self.request.GET.get('quantity_max')
        if quantity_max:
            queryset = queryset.filter(quantity_ordered__lte=quantity_max)
            
        return queryset
    
    def get_context_data(self, **kwargs):
        # --- Your original context data logic is preserved ---
        context = super().get_context_data(**kwargs)
        context['filter_config'] = [
            {
                'name': 'status',
                'label': 'الحالة',
                'placeholder': 'جميع الحالات',
                'options': [
                    {'value': choice[0], 'label': choice[1]} 
                    for choice in ProductionOrder.STATUS_CHOICES
                ]
            },
            {
                'name': 'priority',
                'label': 'الأولوية',
                'placeholder': 'جميع الأولويات',
                'options': [
                    {'value': choice[0], 'label': choice[1]} 
                    for choice in ProductionOrder.PRIORITY_CHOICES
                ]
            }
        ]
        context['search_enabled'] = True
        context['search_placeholder'] = 'البحث برقم الأمر، رقم الباتش، أو اسم المنتج...'
        context['total_count'] = self.get_queryset().count()
        context['search'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['priority_filter'] = self.request.GET.get('priority', '')
        context['users'] = User.objects.filter(is_active=True)
        context['product_categories'] = Category.objects.all()
        return context


class ProductionOrderDetailView(LoginRequiredMixin, DetailView):
    model = ProductionOrder
    template_name = 'production/order_detail.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_object()
        
        # --- Fetch all related processes with prefetching for performance ---
        context['cutting_process'] = CuttingProcess.objects.select_related('cutter').filter(production_order=order).first()
        
        # Prefetch nested relationships for efficiency
        context['assembly_processes'] = order.assembly_processes.select_related(
            'external_manufacturer', 'assembler'
        ).prefetch_related(
            'dyeing_processes__dyeing_facility',
            'dyeing_processes__finishing_process__external_manufacturer',
            'dyeing_processes__finishing_process__finisher',
            'dyeing_processes__finishing_process__supervisor',
            'dyeing_processes__finishing_process__destination_warehouse'
        ).all()
        
        # Other related data
        context['quality_checks'] = order.quality_checks.all()
        context['exit_permits'] = order.exit_permits.all()
        context['cost_analysis'] = getattr(order, 'cost_analysis', None)
        
        # Check if a Bill of Materials exists for the product
        context['bom_exists'] = BillOfMaterials.objects.filter(product=order.product).exists()
        
        return context
# Add this to the existing ProductionOrderCreateView and ProductionOrderUpdateView

class ProductionOrderCreateView(LoginRequiredMixin, CreateView):
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = 'production/order_form.html'
    success_url = reverse_lazy('production:order_list')

    def form_valid(self, form):
        # This logic remains the same
        required_fabric = form.cleaned_data.get('fabric_meters_allocated')
        selected_stock = form.cleaned_data.get('textile_stock')

        if selected_stock.available_quantity < required_fabric:
            form.add_error('textile_stock', f'الكمية غير كافية في هذا المخزون. المتاح: {selected_stock.available_quantity}')
            return self.form_invalid(form)

        form.instance.created_by = self.request.user
        messages.success(self.request, 'تم إنشاء أمر الإنتاج بنجاح.')
        return super().form_valid(form)

    def form_invalid(self, form):
        """
        FIX: This method is overridden to catch form validation errors
        and pass them to the Django messages framework, which will then
        be displayed as toast notifications by the frontend.
        """
        # Loop through all errors in the form
        for field, errors in form.errors.items():
            for error in errors:
                # Get the user-friendly label for the field
                field_label = form.fields[field].label if field != '__all__' else 'خطأ عام في النموذج'
                # Add the error to the messages framework
                messages.error(self.request, f"{field_label}: {error}")
        
        # Continue with the default invalid form handling (re-rendering the page)
        return super().form_invalid(form)

class ProductionOrderUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = 'production/order_form.html'
    
    def get_success_url(self):
        return reverse_lazy('production:order_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        # This logic remains the same
        if self.request.POST.get('auto_save'):
            try:
                self.object = form.save()
                return JsonResponse({
                    'success': True,
                    'message': 'تم الحفظ التلقائي بنجاح'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })
        
        messages.success(self.request, 'تم تحديث أمر الإنتاج بنجاح.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """
        FIX: This method is updated to also handle standard form submissions,
        not just AJAX auto-saves.
        """
        if self.request.POST.get('auto_save'):
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })
        
        # Loop through all errors in the form
        for field, errors in form.errors.items():
            for error in errors:
                # Get the user-friendly label for the field
                field_label = form.fields[field].label if field != '__all__' else 'خطأ عام في النموذج'
                # Add the error to the messages framework
                messages.error(self.request, f"{field_label}: {error}")
        
        # Continue with the default invalid form handling
        return super().form_invalid(form)

class ProductionOrderDeleteView(LoginRequiredMixin, DeleteView):
    model = ProductionOrder
    template_name = 'production/order_confirm_delete.html'
    success_url = reverse_lazy('production:order_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف أمر الإنتاج بنجاح.')
        return super().delete(request, *args, **kwargs)

# Action Views for Production Orders
@login_required
def approve_production_order(request, pk):
    """
    Approves a production order, validates stock, and crucially,
    links the currently active Bill of Materials (BOM) to the order.
    """
    order = get_object_or_404(ProductionOrder, pk=pk)

    # --- FIX: Improved status check and error message ---
    if order.status == 'approved':
        messages.info(request, f'هذا الأمر ({order.order_number}) معتمد بالفعل. الخطوة التالية هي بدء الإنتاج.')
        return redirect('production:order_detail', pk=pk)
    
    if order.status not in ['draft', 'pending']:
        messages.error(request, 'لا يمكن اعتماد هذا الأمر في حالته الحالية لأنه ليس في مرحلة المسودة أو المراجعة.')
        return redirect('production:order_detail', pk=pk)

    try:
        # Find the single active BOM for the product
        active_bom = BillOfMaterials.objects.get(product=order.product, is_active=True)
    except BillOfMaterials.DoesNotExist:
        messages.error(request, f'لا توجد قائمة مواد (BOM) نشطة للمنتج {order.product.name}. يرجى إنشاء وتفعيل واحدة أولاً.')
        return redirect('production:order_detail', pk=pk)
    
    # Link the found BOM to the production order
    order.bom_version = active_bom
    order.status = 'approved'
    order.approved_by = request.user
    order.approved_at = timezone.now()
    order.save()

    messages.success(request, f'تم اعتماد أمر الإنتاج {order.order_number} وربطه بنجاح مع BOM v{active_bom.version}.')
    return redirect('production:order_detail', pk=pk)





@login_required
def complete_production_order(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if order.status in ['in_finishing', 'quality_check']:
        order.status = 'completed'
        order.actual_completion_date = timezone.now().date()
        order.save()
        messages.success(request, f'تم إكمال أمر الإنتاج {order.order_number}.')
    else:
        messages.error(request, 'لا يمكن إكمال هذا الأمر في حالته الحالية.')
    
    return redirect('production:order_detail', pk=pk)

# Textile Stock Views

# Finished Product Views

# Cutting Process Views

class CuttingProcessListView(LoginRequiredMixin, ListView):
    template_name = 'production/cutting_list.html'
    context_object_name = 'cutting_items'
    paginate_by = 15

    def get_queryset(self):
        # Get filter parameters from the request URL
        search_query = self.request.GET.get('search', '').strip()
        status_filter = self.request.GET.get('status', '').strip()

        # Base querysets
        pending_orders = ProductionOrder.objects.filter(
            status='approved', cutting_process__isnull=True
        ).select_related('product')

        existing_processes = CuttingProcess.objects.select_related(
            'production_order__product', 'cutter'
        )

        # Apply search filter to the base querysets for efficiency
        if search_query:
            pending_orders = pending_orders.filter(
                Q(order_number__icontains=search_query) | Q(product__name__icontains=search_query)
            )
            existing_processes = existing_processes.filter(
                Q(production_order__order_number__icontains=search_query) | Q(production_order__product__name__icontains=search_query)
            )

        # Build the unified list from the (potentially filtered) querysets
        unified_list = []
        for order in pending_orders:
            unified_list.append({
                'type': 'pending_order', 'obj': order, 'date': order.approved_at or order.start_date,
                'status_key': 'waiting', 'status_display': 'في انتظار القص',
            })

        for process in existing_processes:
            unified_list.append({
                'type': 'process', 'obj': process, 'date': process.cutting_date,
                'status_key': 'completed' if process.is_completed else 'in_progress',
                'status_display': 'مكتمل' if process.is_completed else 'قيد التنفيذ',
            })
        
        # Apply status filter to the final Python list
        if status_filter:
            unified_list = [item for item in unified_list if item['status_key'] == status_filter]

        # Sort the final list by date
        unified_list.sort(key=lambda x: x['date'] if x['date'] else timezone.now(), reverse=True)
        
        return unified_list

    def get_context_data(self, **kwargs):
        # Manually handle pagination for the combined list
        queryset = self.get_queryset()
        paginator = Paginator(queryset, self.paginate_by)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = super().get_context_data(object_list=page_obj, **kwargs)
        
        # Pass filter configuration and current values to the template
        context.update({
            'cutting_items': page_obj.object_list,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages(),
            'total_count': len(queryset),
            'search_enabled': True,
            'search_placeholder': 'ابحث برقم الأمر أو اسم المنتج...',
            'filters': [
                {
                    'name': 'status',
                    'label': 'الحالة',
                    'placeholder': 'جميع الحالات',
                    'options': [
                        {'value': 'waiting', 'label': 'في انتظار القص'},
                        {'value': 'in_progress', 'label': 'قيد التنفيذ'},
                        {'value': 'completed', 'label': 'مكتمل'},
                    ],
                    'current_value': self.request.GET.get('status', '')
                }
            ]
        })
        return context

@login_required
def get_draws_for_order_ajax(request):
    order_id = request.GET.get('order_id')
    draws_data = []
    if order_id:
        try:
            order = ProductionOrder.objects.select_related('bom_version').get(id=order_id)
            if order.bom_version:
                draws = GarmentDraw.objects.filter(bom=order.bom_version).prefetch_related('pieces')
                for draw in draws:
                    draws_data.append({
                        'size': draw.size, 'notes': draw.notes,
                        'pieces': [{'name': piece.name, 'quantity': piece.quantity} for piece in draw.pieces.all()]
                    })
        except ProductionOrder.DoesNotExist:
            pass 
    return JsonResponse({'draws': draws_data})


class CuttingProcessSharedMixin:
    """ Shares logic between Create and Update views for CuttingProcess. """
    model = CuttingProcess
    form_class = CuttingProcessForm
    template_name = 'production/cutting_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['production_order_queryset'] = ProductionOrder.objects.filter(status='approved')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = getattr(self.object, 'production_order', None)
        if not order and self.request.GET.get('order_id'):
                order = get_object_or_404(ProductionOrder.objects.select_related('product', 'bom_version__size_group'), pk=self.request.GET.get('order_id'))

        if self.request.POST:
            # On POST, the original formset works correctly
            context['cutting_table_formset'] = CuttingTableFormSet(self.request.POST, instance=self.object, prefix='tables')
            if self.object and self.object.is_completed:
                context['cut_piece_formset'] = CutPieceFormSet(self.request.POST, instance=self.object, prefix='pieces')
        else:
            # On GET, dynamically set the 'extra' parameter
            has_tables = self.object.cutting_tables.exists() if self.object else False
            
            # Create a dynamic formset class with the correct 'extra' value
            DynamicCuttingTableFormSet = inlineformset_factory(
                CuttingProcess,
                CuttingTable,
                form=CuttingTableForm,
                extra=0 if has_tables else 1, # The fix is here
                can_delete=True,
                fk_name='cutting_process'
            )
            context['cutting_table_formset'] = DynamicCuttingTableFormSet(instance=self.object, prefix='tables')
            
            # Handle the cut_piece_formset for completed processes
            if self.object and self.object.is_completed:
                context['cut_piece_formset'] = CutPieceFormSet(instance=self.object, prefix='pieces')

        # --- FIX START ---
        # The error was here. The correct way to get the size group is through the
        # production order's linked Bill of Materials (bom_version), not directly from the product.
        if order and order.bom_version and order.bom_version.size_group:
            context['available_sizes'] = order.bom_version.size_group.sizes
        else:
            context['available_sizes'] = []
        # --- FIX END ---
            
        if self.object and self.object.marker_details:
                context['marker_sizes_str'] = ','.join(self.object.marker_details.get('sizes', []))
        return context
        
    def form_valid(self, form):
        context = self.get_context_data()
        table_formset = context['cutting_table_formset']
        cut_piece_formset = context.get('cut_piece_formset')

        marker_sizes_str = self.request.POST.get('marker_sizes', '').strip()
        if not marker_sizes_str:
            form.add_error(None, "الرجاء اختيار أو إدخال المقاسات في حقل 'مقاسات الرسمة'.")
            return self.form_invalid(form)
            
        marker_sizes_list = [size.strip() for size in marker_sizes_str.split(',') if size.strip()]
        marker_details_data = {"sizes": marker_sizes_list, "pieces_per_layer": len(marker_sizes_list)}

        if table_formset.is_valid() and (cut_piece_formset is None or cut_piece_formset.is_valid()):
            with transaction.atomic():
                self.object = form.save(commit=False)
                if not getattr(self.object, 'cutter', None): self.object.cutter = self.request.user
                self.object.marker_details = marker_details_data
                
                self.object.save()

                table_formset.instance = self.object
                table_formset.save()
                if cut_piece_formset:
                    cut_piece_formset.instance = self.object
                    cut_piece_formset.save()

                self.object.refresh_from_db()
                aggregates = self.object.cutting_tables.aggregate(total_fabric=Sum('fabric_length'), total_garments=Sum('total_pieces'))
                self.object.total_fabric_used = aggregates.get('total_fabric') or 0
                self.object.total_pieces_cut = aggregates.get('total_garments') or 0
                self.object.save()

                messages.success(self.request, 'تم حفظ عملية القص بنجاح.')
                return redirect(self.get_success_url())
        else:
            messages.error(self.request, "يرجى تصحيح الأخطاء في البيانات المدخلة.")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('production:cutting_detail', kwargs={'pk': self.object.pk})

class CuttingProcessCreateView(LoginRequiredMixin, CreateView):
    """
    Handles the creation of a new Cutting Process.
    This view is the new "start production" trigger.
    """
    model = CuttingProcess
    form_class = CuttingProcessForm
    template_name = 'production/cutting_form.html'

    def get_initial(self):
        """Pre-populates the form with the order_id from the URL."""
        initial = super().get_initial()
        order_id = self.request.GET.get('order_id')
        if order_id:
            order = get_object_or_404(ProductionOrder, pk=order_id, status='approved')
            initial['production_order'] = order
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Only show 'approved' orders that don't already have a cutting process
        kwargs['production_order_queryset'] = ProductionOrder.objects.filter(
            status='approved', cutting_process__isnull=True
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['cutting_table_formset'] = CuttingTableFormSet(self.request.POST, prefix='tables')
        else:
            context['cutting_table_formset'] = CuttingTableFormSet(prefix='tables')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        table_formset = context['cutting_table_formset']

        marker_sizes_str = self.request.POST.get('marker_sizes', '').strip()
        if not marker_sizes_str:
            form.add_error(None, "الرجاء اختيار أو إدخال المقاسات في حقل 'مقاسات الرسمة'.")
            return self.form_invalid(form)

        if not table_formset.is_valid():
            messages.error(self.request, "يرجى تصحيح الأخطاء في جداول القص.")
            return self.form_invalid(form)

        with transaction.atomic():
            # 1. Save the new CuttingProcess instance
            self.object = form.save(commit=False)
            if not getattr(self.object, 'cutter', None):
                self.object.cutter = self.request.user
            
            marker_sizes_list = [size.strip() for size in marker_sizes_str.split(',') if size.strip()]
            self.object.marker_details = {"sizes": marker_sizes_list, "pieces_per_layer": len(marker_sizes_list)}
            self.object.save() # Save to get a PK for the formset

            # 2. Save the related cutting tables
            table_formset.instance = self.object
            table_formset.save()

            # 3. Recalculate totals and save again
            self.object.refresh_from_db()
            aggregates = self.object.cutting_tables.aggregate(total_fabric=Sum('fabric_length'), total_garments=Sum('total_pieces'))
            self.object.total_fabric_used = aggregates.get('total_fabric') or 0
            self.object.total_pieces_cut = aggregates.get('total_garments') or 0
            self.object.save()

            # 4. **CRITICAL STEP**: Update the Production Order status
            production_order = self.object.production_order
            if production_order.status == 'approved':
                production_order.status = 'in_cutting'
                production_order.save(update_fields=['status'])

            messages.success(self.request, f'تم بدء عملية القص لأمر الإنتاج {production_order.order_number} بنجاح.')
            return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('production:cutting_detail', kwargs={'pk': self.object.pk})

class CuttingProcessUpdateView(CuttingProcessSharedMixin, UpdateView):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs['production_order_queryset'] = ProductionOrder.objects.filter(pk=self.object.production_order.pk)
        return kwargs

@require_POST
@login_required
def update_cut_piece_quantity_ajax(request):
    try:
        cut_piece_id = request.POST.get('cut_piece_id')
        new_quantity = int(request.POST.get('quantity'))

        if new_quantity < 0:
            return JsonResponse({'success': False, 'error': 'الكمية لا يمكن أن تكون سالبة.'}, status=400)
            
        cut_piece = get_object_or_404(CutPiece, id=cut_piece_id)
        cut_piece.quantity = new_quantity
        cut_piece.save(update_fields=['quantity'])
        
        return JsonResponse({'success': True, 'message': 'تم تحديث الكمية.'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'قيمة الكمية غير صحيحة.'}, status=400)
    except CutPiece.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'قطعة القص غير موجودة.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def complete_cutting_process(request, pk):
    """
    Handles the completion of a cutting process.
    This view now explicitly contains the logic that was previously in signals,
    making the process transparent and robust.
    """
    cutting_process = get_object_or_404(CuttingProcess, pk=pk)
    production_order = cutting_process.production_order

    # Step 1: Initial Validation
    # Check if the process is already marked as completed to prevent re-running.
    if cutting_process.is_completed:
        messages.info(request, 'عملية القص هذه مكتملة بالفعل.')
        return redirect('production:cutting_detail', pk=pk)

    # Check if the necessary cutting data (marker details) has been entered.
    if not cutting_process.marker_details or not cutting_process.marker_details.get('sizes'):
        messages.error(request, 'لا يمكن إكمال العملية. تفاصيل الرسمة (المقاسات) غير محددة.')
        return redirect('production:cutting_update', pk=pk)

    try:
        # Step 2: Use a database transaction for safety.
        # If any step inside this 'with' block fails, all database changes will be automatically rolled back.
        with transaction.atomic():
            
            # Step 3: Generate the inventory of all cut pieces.
            # First, clear any existing pieces for this process to prevent duplicates.
            cutting_process.cut_pieces.all().delete()
            
            # Calculate the total number of fabric layers used across all cutting tables.
            total_layers = cutting_process.cutting_tables.aggregate(total=Sum('layers_count'))['total'] or 0
            if total_layers == 0:
                messages.error(request, 'لا يمكن إكمال العملية. لم يتم تسجيل أي طبقات في جداول القص.')
                raise ValueError("No layers in cutting table.")

            # Get the list of sizes from the marker details.
            marker_sizes = cutting_process.marker_details.get('sizes', [])
            size_counts_in_marker = Counter(marker_sizes)
            all_required_sizes = set(size_counts_in_marker.keys())
            
            # Get the Bill of Materials linked to the production order.
            product_bom = production_order.bom_version
            if not product_bom:
                 messages.error(request, f"أمر الإنتاج #{production_order.order_number} غير مرتبط بقائمة مواد (BOM).")
                 raise ValueError("BOM not linked to production order.")

            # Find the specific cutting patterns (GarmentDraw) for the required sizes.
            draws_for_bom = GarmentDraw.objects.filter(bom=product_bom, size__in=all_required_sizes).prefetch_related('pieces')
            found_draws_by_size = {draw.size: draw for draw in draws_for_bom}
            
            # Prepare a list of all CutPiece objects to be created.
            pieces_to_create = []
            for size, count_in_marker in size_counts_in_marker.items():
                draw = found_draws_by_size.get(size)
                if draw:
                    for draw_piece in draw.pieces.all():
                        total_quantity = total_layers * count_in_marker * draw_piece.quantity
                        if total_quantity > 0:
                            pieces_to_create.append(
                                CutPiece(cutting_process=cutting_process, piece_type=draw_piece.name, size=size, quantity=total_quantity)
                            )
                else:
                    # If no specific draw is found, create pieces based on a standard jeans structure.
                    standard_jeans_pieces = [
                        {'name': 'ظهر يمين', 'quantity': 1},
                        {'name': 'ظهر شمال', 'quantity': 1},
                        {'name': 'سدر يمين', 'quantity': 1},
                        {'name': 'سدر شمال', 'quantity': 1},
                        {'name': 'كمر', 'quantity': 1},
                        {'name': 'باليتة سوستة', 'quantity': 1},
                        {'name': 'جيب أمامي', 'quantity': 2},
                        {'name': 'جيب خلفي', 'quantity': 2},
                        {'name': 'بطانة جيب', 'quantity': 4},
                        {'name': 'كسر سوستة', 'quantity': 1},
                        {'name': 'جيب ساعة', 'quantity': 1},
                        {'name': 'دوبلير كمر', 'quantity': 1},
                    ]
                    for piece_data in standard_jeans_pieces:
                        total_quantity = total_layers * count_in_marker * piece_data['quantity']
                        if total_quantity > 0:
                            pieces_to_create.append(
                                CutPiece(
                                    cutting_process=cutting_process,
                                    piece_type=piece_data['name'],
                                    size=size,
                                    quantity=total_quantity
                                )
                            )

            if pieces_to_create:
                CutPiece.objects.bulk_create(pieces_to_create)
            else:
                messages.warning(request, "لم يتم توليد أي قطع. قد يكون السبب عدم وجود رسومات قص أو طبقات في جداول القص.")

                        # Define the specific pieces for jeans and their quantities
                        

            # Step 4: Deduct the used fabric from the warehouse stock.
            total_fabric_used = getattr(cutting_process, 'total_fabric_used', Decimal('0.0'))
            fabric_stock_item = production_order.textile_stock 

            if total_fabric_used > 0 and fabric_stock_item:
                # Create an explicit, auditable record of the stock movement.
                StockMovement.objects.create(
                    stock_item=fabric_stock_item,
                    movement_type='out',
                    quantity=total_fabric_used,
                    reference_number=f"CUT-{production_order.order_number}",
                    notes=f"استهلاك قماش لعملية القص لأمر الإنتاج #{production_order.order_number}",
                    created_by=request.user
                )
            
            # Step 5: Finalize the process and update the order status.
            cutting_process.is_completed = True
            cutting_process.completed_at = timezone.now()
            cutting_process.save()

            final_cut_quantity = cutting_process.total_pieces_cut

            if final_cut_quantity > 0:
                original_quantity = production_order.quantity_ordered
                # Update the production order quantity to the actual cut quantity
                production_order.quantity_ordered = final_cut_quantity
                # Advance the status
                production_order.status = 'in_assembly'
                # Save both fields in a single operation
                production_order.save(update_fields=['quantity_ordered', 'status'])
                
                # Inform the user about the automatic change
                messages.info(request, f"تم تحديث الكمية المطلوبة في أمر الإنتاج #{production_order.order_number} من {original_quantity} إلى {final_cut_quantity} بناءً على إجمالي القطع المقصوصة.")
            else:
                 # Fallback: if no pieces were cut for some reason, just advance the status.
                 production_order.status = 'in_assembly'
                 production_order.save(update_fields=['status'])

            messages.success(request, f'اكتملت عملية القص! تم توليد {len(pieces_to_create)} نوع من القطع وتحديث مخزون القماش.')

    except ValueError as e:
        # This will catch our custom validation errors and prevent redirection.
        # The transaction is automatically rolled back on any exception.
        pass # The error message is already in the `messages` framework.
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")

    return redirect('production:cutting_detail', pk=pk)


class CuttingProcessDetailView(LoginRequiredMixin, DetailView):
    model = CuttingProcess
    template_name = 'production/cutting_detail.html'
    context_object_name = 'cutting_process'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cutting_process = self.get_object()
        
        context['cutting_tables'] = cutting_process.cutting_tables.all()
        context['cut_pieces'] = cutting_process.cut_pieces.order_by('piece_type', 'size')
        
        # Calculate new, more accurate stats
        total_individual_pieces = context['cut_pieces'].aggregate(total=Sum('quantity'))['total'] or 0
        
        context['cutting_stats'] = {
            'total_tables': context['cutting_tables'].count(),
            'total_garments': cutting_process.total_pieces_cut,
            'total_individual_pieces': total_individual_pieces,
        }
        return context


class AssemblyProcessListView(LoginRequiredMixin, ListView):
    model = AssemblyProcess
    template_name = 'production/assembly_list.html'
    context_object_name = 'assembly_processes'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = AssemblyProcess.objects.select_related(
            'production_order', 'production_order__product', 
            'external_manufacturer', 'assembler'
        ).order_by('-start_date')
        
        # تصفية حسب نوع التجميع
        assembly_type = self.request.GET.get('assembly_type')
        if assembly_type:
            queryset = queryset.filter(assembly_type=assembly_type)
        
        # تصفية حسب الحالة
        status = self.request.GET.get('status')
        if status == 'completed':
            queryset = queryset.filter(is_completed=True)
        elif status == 'pending':
            queryset = queryset.filter(is_completed=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assembly_types'] = AssemblyProcess.ASSEMBLY_TYPES
        context['assembly_type_filter'] = self.request.GET.get('assembly_type', '')
        context['status_filter'] = self.request.GET.get('status', '')
        return context

class AssemblyProcessCreateView(LoginRequiredMixin, CreateView):
    model = AssemblyProcess
    form_class = AssemblySendForm
    template_name = 'production/assembly_form.html'

    # ... get_initial and get_form_kwargs remain the same ...
    def get_initial(self):
        initial = super().get_initial()
        order_id = self.request.GET.get('order_id')
        if order_id:
            try:
                order = ProductionOrder.objects.get(pk=order_id, status='in_assembly')
                initial['production_order'] = order
            except ProductionOrder.DoesNotExist:
                pass
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['available_orders'] = ProductionOrder.objects.filter(status='in_assembly').select_related('product')
        return kwargs


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['component_formset'] = CustomAssemblyComponentFormSet(self.request.POST, prefix='components')
        else:
            context['component_formset'] = CustomAssemblyComponentFormSet(prefix='components', queryset=AssemblyComponent.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        component_formset = context['component_formset']

        if not component_formset.is_valid():
            messages.error(self.request, "يرجى تصحيح الأخطاء في قائمة المكونات.")
            # Manually add formset errors to the messages framework for better user feedback
            for fs_form in component_formset:
                 for field, error_list in fs_form.errors.items():
                     for error in error_list:
                         field_label = fs_form.fields[field].label if field != '__all__' else 'خطأ عام'
                         messages.warning(self.request, f"{fs_form.instance.material.name if fs_form.instance.material else ''} - {field_label}: {error}")
            return self.form_invalid(form)

        with transaction.atomic():
            if form.cleaned_data.get('assembly_type') == 'in_house':
                form.instance.assembler = self.request.user
            self.object = form.save()
            
            # --- ENTIRELY NEW LOGIC FOR STOCK WITHDRAWAL ---
            # The old logic is removed and replaced with this more precise one.
            
            component_formset.instance = self.object
            components = component_formset.save(commit=False) # Get instances without committing yet

            for component in components:
                # We only process components that have a quantity and a selected warehouse
                if component.quantity_sent > 0 and component.source_warehouse:
                    component.save() # Now save the component to the DB
                    try:
                        # Get the specific stock item from the selected warehouse
                        stock_item = StockItem.objects.get(
                            product=component.material,
                            warehouse=component.source_warehouse
                        )
                        # Create the stock movement to withdraw the quantity
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type='out',
                            quantity=component.quantity_sent,
                            reference_number=f"ASM-{self.object.id}",
                            notes=f"صرف مكونات من مخزن '{component.source_warehouse.name}' لعملية تجميع #{self.object.id}",
                            created_by=self.request.user
                        )
                    except StockItem.DoesNotExist:
                        # This case should be caught by the formset validation, but it's good to have a safeguard
                        messages.error(self.request, f"خطأ حرج: لم يتم العثور على سجل مخزون للمادة {component.material.name} في مخزن {component.source_warehouse.name}.")
                        # This will roll back the transaction
                        raise ValueError(f"Stock item not found for {component.material.name}")
            
        messages.success(self.request, 'تم إرسال عملية التجميع ومكوناتها بنجاح.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('production:assembly_detail', kwargs={'pk': self.object.pk})

# In production/views.py

class AssemblyProcessDetailView(LoginRequiredMixin, DetailView):
    model = AssemblyProcess
    template_name = 'production/assembly_detail.html'
    context_object_name = 'assembly_process'

    def get_queryset(self):
        # Optimize query by pre-fetching related data needed in the template
        return super().get_queryset().select_related(
            # CORRECTED: The path to size_group is through the order's bom_version
            'production_order__product',
            'production_order__bom_version__size_group', 
            'external_manufacturer',
            'assembler'
        ).prefetch_related(
            'components__material__unit_new'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assembly_process = self.get_object()

        context['sent_components'] = assembly_process.components.all()
        context['exit_permit'] = ExitPermit.objects.filter(assembly_process=assembly_process).first()
        context['dyeing_process_exists'] = assembly_process.dyeing_processes.exists()
        context['receive_form'] = AssemblyReceiveForm(instance=assembly_process)
        
        context['assembly_stats'] = {
            'defect_rate': assembly_process.defect_rate,
            'loss_rate': assembly_process.loss_rate,
            'efficiency': (
                (assembly_process.quantity_received / assembly_process.quantity_sent) * 100
                if assembly_process.quantity_sent > 0 else 0
            ),
        }
        
        if assembly_process.assembly_type == 'outsourced' and not context['exit_permit']:
            production_order = assembly_process.production_order
            product = production_order.product
            
            # CORRECTED: Get the size group from the order's specific BOM version
            bom = production_order.bom_version
            size_group = bom.size_group if bom else None
            
            description_parts = [f"قطع جاهزة للتجميع للمنتج: {product.name} (أمر #{production_order.order_number})"]
            if size_group:
                sizes_str = ", ".join(size_group.sizes)
                description_parts.append(f"مجموعة المقاسات: {size_group.name} ({sizes_str})")
            
            if context['sent_components']:
                description_parts.append("\n--- مكونات إضافية مرسلة ---")
                for comp in context['sent_components']:
                    unit_name = comp.material.unit_new.symbol if comp.material.unit_new else 'وحدة'
                    description_parts.append(f"- {comp.material.name}: {comp.quantity_sent} {unit_name}")

            initial_data = {
                'production_order': production_order,
                'permit_type': 'assembly_pieces',
                'items_description': "\n".join(description_parts),
                'quantity': assembly_process.quantity_sent,
                'destination': assembly_process.external_manufacturer.name if assembly_process.external_manufacturer else '',
                'purpose': 'إرسال للتجميع الخارجي',
                'valid_until': timezone.now() + timedelta(days=7)
            }
            context['exit_permit_form'] = ExitPermitForm(initial=initial_data)

        return context

class AssemblyProcessUpdateView(LoginRequiredMixin, UpdateView):
    model = AssemblyProcess
    form_class = AssemblySendForm
    template_name = 'production/assembly_form.html'

    def get_queryset(self):
        return super().get_queryset().filter(is_completed=False)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs['available_orders'] = ProductionOrder.objects.filter(pk=self.object.production_order.pk)
        return kwargs

    def get_success_url(self):
        return reverse_lazy('production:assembly_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if form.cleaned_data.get('assembly_type') == 'in_house':
            form.instance.assembler = self.request.user
            form.instance.external_manufacturer = None
        else:
            form.instance.assembler = None
        messages.success(self.request, 'تم تحديث بيانات إرسال التجميع بنجاح.')
        return super().form_valid(form)

    # --- ADD THIS METHOD ---
    def form_invalid(self, form):
        """
        Catches form validation errors and adds them to the messages framework
        so they can be displayed as toast notifications.
        """
        # Create a single, readable error message from all form errors.
        error_list = []
        for field, errors in form.errors.items():
            if field == '__all__':
                error_list.extend(errors)
            else:
                # Get the field's user-friendly label
                label = form.fields.get(field).label if form.fields.get(field) else field
                error_list.extend([f"{label}: {error}" for error in errors])
        
        error_string = " ".join(error_list)
        messages.error(self.request, f"فشل الحفظ. الرجاء تصحيح الأخطاء: {error_string}")

        # Allow the default form_invalid behavior to continue, which re-renders the page with the form.
        return super().form_invalid(form)

@login_required
def ajax_get_bom_components_for_order(request):
    """
    AJAX view to fetch BOM components for a given production order.
    FIXED: This version now correctly queries and structures warehouse stock data for the frontend.
    """
    order_id = request.GET.get('order_id')
    if not order_id:
        return JsonResponse({'error': 'Order ID required'}, status=400)

    try:
        order = ProductionOrder.objects.select_related('bom_version').get(pk=order_id)
        if not order.bom_version:
            return JsonResponse({'error': 'لا توجد قائمة مواد (BOM) نشطة مرتبطة بأمر الإنتاج هذا.', 'components': []})

        # Get all relevant warehouses once. This is efficient.
        raw_material_warehouses = Warehouse.objects.filter(
            warehouse_type__in=['components', 'textile'], is_active=True
        )
        
        # Get all items for the BOM, prefetching related data.
        bom_items = order.bom_version.items.select_related('material', 'material__unit_new').all()
        
        components = []
        for item in bom_items:
            # 1. Get all existing stock items for the current material.
            existing_stock_items = StockItem.objects.filter(
                product=item.material,
                warehouse__in=raw_material_warehouses
            )
            # 2. Create a dictionary for quick lookup of available stock by warehouse ID.
            stock_by_warehouse_id = {si.warehouse_id: si.available_quantity for si in existing_stock_items}
            
            # 3. Calculate total available stock across all found items.
            total_available = sum(stock_by_warehouse_id.values())

            # 4. Build the warehouses_data list by iterating through ALL potential warehouses,
            #    ensuring that warehouses with zero stock are also included in the dropdown.
            warehouses_data = []
            for warehouse in raw_material_warehouses:
                warehouses_data.append({
                    'id': warehouse.id,
                    'name': warehouse.name,
                    # Look up the quantity from our dictionary, defaulting to 0 if not found.
                    'available_quantity': float(stock_by_warehouse_id.get(warehouse.id, Decimal('0.0')))
                })

            components.append({
                'material_id': item.material.id,
                'name': item.material.name,
                'total_required': float(item.quantity * order.quantity_ordered),
                'total_available_stock': float(total_available),
                'unit': item.material.unit_new.symbol if item.material.unit_new else 'units',
                'warehouses': warehouses_data, # This is the crucial list for the frontend.
            })
            
        return JsonResponse({'components': components})

    except ProductionOrder.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    except Exception as e:
        logging.error(f"Error in ajax_get_bom_components_for_order: {e}")
        return JsonResponse({'error': 'An unexpected error occurred while fetching BOM components.'}, status=500)


@login_required
def get_stock_for_material_in_warehouse_ajax(request):
    material_id = request.GET.get('material_id')
    warehouse_id = request.GET.get('warehouse_id')

    if not all([material_id, warehouse_id]):
        return JsonResponse({'error': 'Material and Warehouse IDs are required.'}, status=400)

    try:
        stock_item = StockItem.objects.get(product_id=material_id, warehouse_id=warehouse_id)
        return JsonResponse({'available_stock': stock_item.available_quantity})
    except StockItem.DoesNotExist:
        return JsonResponse({'available_stock': 0})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta
# ... other existing imports


@login_required
@require_POST
def receive_assembly_process(request, pk):
    """
    Handles receiving items from assembly.
    FIX: Now correctly calculates the cost before creating the financial transaction.
    """
    assembly_process = get_object_or_404(AssemblyProcess, pk=pk, is_completed=False)
    form = AssemblyReceiveForm(request.POST, instance=assembly_process)

    if form.is_valid():
        with transaction.atomic():
            process = form.save(commit=False)
            process.is_completed = True
            process.actual_completion_date = timezone.now()
            
            # --- FIX: Explicitly calculate the cost here in the view ---
            cost = Decimal('0.00')
            if process.assembly_type == 'outsourced' and process.external_manufacturer and process.quantity_received > 0:
                try:
                    price_record = ManufacturerProductPrice.objects.get(
                        manufacturer=process.external_manufacturer,
                        product=process.production_order.product
                    )
                    # Cost is price per piece * quantity received
                    cost = price_record.price * process.quantity_received
                except ManufacturerProductPrice.DoesNotExist:
                    messages.warning(request, f"No price set for product '{process.production_order.product.name}' with manufacturer '{process.external_manufacturer.name}'. Cost will be zero.")
            
            process.assembly_cost = cost
            process.save() # Save the process with the final cost

            # FINANCIAL LOGIC
            if process.assembly_type == 'outsourced' and process.external_manufacturer and process.assembly_cost > 0:
                success = create_invoice_and_transaction(
                    request=request,
                    process_instance=process,
                    manufacturer=process.external_manufacturer,
                    cost=process.assembly_cost,
                    expense_name=_("Outsourced Assembly Costs"),
                    notes=_("تكلفة تجميع: {prod_name} ({qty} قطعة)").format(
                        prod_name=process.production_order.product.name,
                        qty=process.quantity_received
                    )
                )
                if not success:
                    raise ValueError("Failed to create financial records for assembly.")

            process.production_order.status = 'in_dyeing'
            process.production_order.save(update_fields=['status'])
            messages.success(request, _('Assembly process for order {order_num} has been successfully received.').format(
                order_num=process.production_order.order_number
            ))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{form.fields[field].label}: {error}")

    return redirect('production:assembly_detail', pk=pk)


@login_required
def complete_assembly_process(request, pk):
    assembly_process = get_object_or_404(AssemblyProcess, pk=pk)
    
    if not assembly_process.is_completed:
        assembly_process.is_completed = True
        assembly_process.actual_completion_date = timezone.now()
        assembly_process.save()
        
        # حساب تكلفة التجميع
        assembly_process.calculate_assembly_cost()
        
        # تحديث حالة أمر الإنتاج
        assembly_process.production_order.status = 'in_dyeing'
        assembly_process.production_order.save()
        
        messages.success(request, f'تم إكمال عملية التجميع لأمر الإنتاج {assembly_process.production_order.order_number}.')
    else:
        messages.error(request, 'عملية التجميع مكتملة بالفعل.')
    
    return redirect('production:assembly_detail', pk=pk)

# Dyeing Process Views
class DyeingProcessListView(LoginRequiredMixin, ListView):
    model = DyeingProcess
    template_name = 'production/dyeing_list.html'
    context_object_name = 'dyeing_processes'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = DyeingProcess.objects.select_related(
            'assembly_process__production_order__product', 'dyeing_facility'
        ).order_by('-sent_date')
        
        # Search functionality
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(assembly_process__production_order__order_number__icontains=search_query) |
                Q(assembly_process__production_order__product__name__icontains=search_query) |
                Q(dyeing_facility__name__icontains=search_query)
            )

        # Filter by status
        status = self.request.GET.get('status')
        if status == 'completed':
            queryset = queryset.filter(is_completed=True)
        elif status == 'pending':
            queryset = queryset.filter(is_completed=False)
        
        # Filter by facility
        facility_id = self.request.GET.get('facility')
        if facility_id:
            queryset = queryset.filter(dyeing_facility_id=facility_id)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['facilities'] = ExternalManufacturer.objects.filter(dyeing_jobs__isnull=False).distinct()
        return context



class DyeingProcessCreateView(LoginRequiredMixin, CreateView):
    model = DyeingProcess
    form_class = DyeingSendForm
    template_name = 'production/dyeing_form.html'



    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['available_assemblies'] = AssemblyProcess.objects.filter(
            is_completed=True, dyeing_processes__isnull=True
        ).select_related('production_order')
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            assembly_process = form.cleaned_data['assembly_process']
            dyeing_facility = form.cleaned_data['dyeing_facility']

            form.instance.quantity_sent = assembly_process.quantity_received
            

            self.object = form.save()

            production_order = assembly_process.production_order
            if production_order.status == 'in_assembly' or production_order.status == 'in_finishing':
                 # This logic allows moving from assembly or creating another dyeing process later
                production_order.status = 'in_dyeing'
                production_order.save(update_fields=['status'])

            messages.success(self.request, 'تم إنشاء عملية الصباغة. يمكنك الآن إنشاء إذن خروج.')
            return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('production:dyeing_detail', kwargs={'pk': self.object.pk})

# In production/views.py

class DyeingProcessDetailView(LoginRequiredMixin, DetailView):
    model = DyeingProcess
    template_name = 'production/dyeing_detail.html'
    context_object_name = 'dyeing_process'

    def get_queryset(self):
        # CORRECTED: The query now follows the correct path to the size_group
        return super().get_queryset().select_related(
            'assembly_process__production_order__product',
            'assembly_process__production_order__bom_version__size_group',
            'dyeing_facility'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dyeing_process = self.get_object()

        context['exit_permit'] = dyeing_process.exit_permits.first()
        context['finishing_process_exists'] = hasattr(dyeing_process, 'finishing_process')

        if not dyeing_process.is_completed:
            context['receive_form'] = DyeingReceiveForm(instance=dyeing_process)

        if not context['exit_permit']:
            production_order = dyeing_process.assembly_process.production_order
            product = production_order.product
            
            # CORRECTED: Get the size group from the order's specific BOM version
            bom = production_order.bom_version
            size_group = bom.size_group if bom else None
            
            description_parts = [f"ملابس جاهزة للصباغة للمنتج: {product.name} (أمر #{production_order.order_number})"]
            if size_group:
                sizes_str = ", ".join(size_group.sizes)
                description_parts.append(f"مجموعة المقاسات: {size_group.name} ({sizes_str})")

            initial_data = {
                'production_order': production_order, # FIX: Add the missing production_order
                'permit_type': 'dyeing_garments',
                'items_description': "\n".join(description_parts),
                'quantity': dyeing_process.quantity_sent,
                'destination': dyeing_process.dyeing_facility.name,
                'purpose': f'إرسال للصباغة - اللون: {dyeing_process.color_specification}',
                'valid_until': timezone.now() + timedelta(days=7)
            }
            context['exit_permit_form'] = ExitPermitForm(initial=initial_data)

        return context

class DyeingProcessUpdateView(LoginRequiredMixin, UpdateView):
    model = DyeingProcess
    form_class = DyeingSendForm
    template_name = 'production/dyeing_form.html'

    def get_queryset(self):
        return super().get_queryset().filter(is_completed=False)

    def get_success_url(self):
        return reverse('production:dyeing_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث بيانات عملية الصباغة بنجاح.')
        return super().form_valid(form)


class DyeingProcessDeleteView(LoginRequiredMixin, DeleteView):
    model = DyeingProcess
    template_name = 'production/dyeing_confirm_delete.html'
    success_url = reverse_lazy('production:dyeing_list')
    context_object_name = 'dyeing_process'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # This is the phrase the user must type to confirm deletion.
        context['confirmation_phrase'] = 'انا متاكد من مسح الصباغه'
        return context

    def form_valid(self, form):
        # Add a success message upon deletion
        messages.success(self.request, f"تم حذف عملية الصباغة الخاصة بأمر '{self.object.assembly_process.production_order.order_number}' بنجاح.")
        return super().form_valid(form)


@login_required
@require_POST
def receive_dyeing_process(request, pk):
    """
    Handles receiving items from the dyeing process.
    FIX: Now correctly calculates the cost before creating the financial transaction.
    """
    dyeing_process = get_object_or_404(DyeingProcess, pk=pk, is_completed=False)
    form = DyeingReceiveForm(request.POST, instance=dyeing_process)

    if form.is_valid():
        with transaction.atomic():
            process = form.save(commit=False)
            process.is_completed = True
            process.actual_return_date = timezone.now()
            
            # FIX: Explicit cost calculation
            process.calculate_total_cost() # This method should use ManufacturerProductPrice
            process.save()

            # FINANCIAL LOGIC
            if process.dyeing_facility and process.total_dyeing_cost > 0:
                success = create_invoice_and_transaction(
                    request=request,
                    process_instance=process,
                    manufacturer=process.dyeing_facility,
                    cost=process.total_dyeing_cost,
                    expense_name=_("Dyeing Costs"),
                    notes=_("Auto-invoice for dyeing process #{id} for order {order_num}").format(
                        id=process.id, order_num=process.assembly_process.production_order.order_number
                    )
                )
                if not success:
                    raise ValueError("Failed to create financial records for dyeing.")

            production_order = process.assembly_process.production_order
            production_order.status = 'in_finishing'
            production_order.save(update_fields=['status'])
            messages.success(request, _("Dyeing process for order {order_num} has been successfully received.").format(
                order_num=production_order.order_number
            ))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{form.fields[field].label}: {error}")

    return redirect('production:dyeing_detail', pk=pk)

# Finishing Process Views
class FinishingProcessListView(LoginRequiredMixin, ListView):
    model = FinishingProcess
    template_name = 'production/finishing_list.html'
    context_object_name = 'finishing_processes'
    paginate_by = 20

    def get_queryset(self):
        queryset = FinishingProcess.objects.select_related(
            'dyeing_process__assembly_process__production_order__product', 
            'external_manufacturer', 'finisher', 'supervisor'
        ).order_by('-start_date')
        # Add filters here if needed (e.g., by status, type)
        return queryset







class FinishingProcessCreateView(LoginRequiredMixin, CreateView):
    model = FinishingProcess
    form_class = FinishingSendForm
    template_name = 'production/finishing_form.html'

    def get_initial(self):
        initial = super().get_initial()
        dyeing_id = self.request.GET.get('dyeing_id')
        if dyeing_id:
            dyeing = get_object_or_404(DyeingProcess, pk=dyeing_id, is_completed=True)
            initial['dyeing_process'] = dyeing
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['available_dyeing'] = DyeingProcess.objects.filter(
            is_completed=True, finishing_process__isnull=True
        ).select_related('assembly_process__production_order')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['component_formset'] = CustomFinishingComponentFormSet(self.request.POST, prefix='components')
        else:
            # When creating, initially show no forms, they will be populated via AJAX
            context['component_formset'] = CustomFinishingComponentFormSet(prefix='components', queryset=FinishingComponent.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        component_formset = context['component_formset']

        if not component_formset.is_valid():
            messages.error(self.request, "يرجى تصحيح الأخطاء في قائمة المكونات.")
            for fs_form in component_formset:
                 for field, error_list in fs_form.errors.items():
                     for error in error_list:
                         field_label = fs_form.fields[field].label if field != '__all__' else 'خطأ عام'
                         messages.warning(self.request, f"{fs_form.instance.material.name if fs_form.instance.material else ''} - {field_label}: {error}")
            return self.form_invalid(form)

        with transaction.atomic():
            dyeing_process = form.cleaned_data['dyeing_process']
            
            if form.cleaned_data.get('finishing_type') == 'in_house':
                form.instance.finisher = self.request.user 
                form.instance.supervisor = self.request.user 
            
            self.object = form.save(commit=False)
            self.object.calculate_total_cost() 
            self.object.save() 

            # Save components and deduct stock
            component_formset.instance = self.object
            components = component_formset.save(commit=False)

            for component in components:
                if component.quantity_sent > 0 and component.source_warehouse:
                    component.save()
                    try:
                        stock_item = StockItem.objects.get(
                            product=component.material,
                            warehouse=component.source_warehouse
                        )
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type='out',
                            quantity=component.quantity_sent,
                            reference_number=f"FIN-{self.object.id}",
                            notes=f"صرف مكونات من مخزن '{component.source_warehouse.name}' لعملية تشطيب #{self.object.id}",
                            created_by=self.request.user
                        )
                    except StockItem.DoesNotExist:
                        messages.error(self.request, f"خطأ حرج: لم يتم العثور على سجل مخزون للمادة {component.material.name} في مخزن {component.source_warehouse.name}.")
                        raise ValueError(f"Stock item not found for {component.material.name}")
            
            production_order = dyeing_process.assembly_process.production_order
            production_order.status = 'in_finishing'
            production_order.save(update_fields=['status'])

            messages.success(self.request, 'تم إنشاء عملية التشطيب بنجاح.')
            return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('production:finishing_detail', kwargs={'pk': self.object.pk})

class FinishingProcessUpdateView(LoginRequiredMixin, UpdateView):
    model = FinishingProcess
    form_class = FinishingSendForm
    template_name = 'production/finishing_form.html'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_completed=False)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs['available_dyeing'] = DyeingProcess.objects.filter(pk=self.object.dyeing_process.pk)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['component_formset'] = CustomFinishingComponentFormSet(self.request.POST, instance=self.object, prefix='components')
        else:
            # For existing components, pre-populate available stock for display
            formset = CustomFinishingComponentFormSet(instance=self.object, prefix='components')
            for form in formset:
                if form.instance.pk and form.instance.material and form.instance.source_warehouse:
                    try:
                        stock_item = StockItem.objects.get(
                            product=form.instance.material,
                            warehouse=form.instance.source_warehouse
                        )
                        # Attach available_quantity directly to the form instance for easy access in template
                        form.instance.available_stock_in_selected_warehouse = stock_item.available_quantity
                    except StockItem.DoesNotExist:
                        form.instance.available_stock_in_selected_warehouse = Decimal('0.0')
                else:
                    form.instance.available_stock_in_selected_warehouse = Decimal('0.0') # Default for new/empty forms
            context['component_formset'] = formset
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        component_formset = context['component_formset']

        if not component_formset.is_valid():
            messages.error(self.request, "يرجى تصحيح الأخطاء في قائمة المكونات.")
            for fs_form in component_formset:
                 for field, error_list in fs_form.errors.items():
                     for error in error_list:
                         field_label = fs_form.fields[field].label if field != '__all__' else 'خطأ عام'
                         messages.warning(self.request, f"{fs_form.instance.material.name if fs_form.instance.material else ''} - {field_label}: {error}")
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save(commit=False) 
            self.object.calculate_total_cost() 
            self.object.save() 

            # Save components and handle stock deduction (for new/updated components)
            component_formset.instance = self.object
            components = component_formset.save(commit=False)

            for component in components:
                # If a component is new or its quantity/warehouse changed, handle stock
                if component.quantity_sent > 0 and component.source_warehouse:
                    component.save() # Save the component first
                    # For simplicity, we're not implementing complex delta logic here.
                    # A more robust system would calculate the difference from old quantity
                    # and create movements accordingly. For now, this assumes new/updated
                    # components trigger new movements.
                    try:
                        stock_item = StockItem.objects.get(
                            product=component.material,
                            warehouse=component.source_warehouse
                        )
                        # This creates a new 'out' movement. If you need to adjust existing,
                        # you'd need to fetch and update/delete previous movements.
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type='out',
                            quantity=component.quantity_sent,
                            reference_number=f"FIN-UPD-{self.object.id}",
                            notes=f"صرف مكونات (تعديل) من مخزن '{component.source_warehouse.name}' لعملية تشطيب #{self.object.id}",
                            created_by=self.request.user
                        )
                    except StockItem.DoesNotExist:
                        messages.error(self.request, f"خطأ حرج: لم يتم العثور على سجل مخزون للمادة {component.material.name} في مخزن {component.source_warehouse.name}.")
                        raise ValueError(f"Stock item not found for {component.material.name}")
            
            # Handle deleted components from the formset
            for obj in component_formset.deleted_objects:
                # If a component was deleted, you might want to return its stock.
                # This is a placeholder; implement stock return logic if needed.
                messages.info(self.request, f"تم حذف المكون {obj.material.name}. (لم يتم إعادة المخزون تلقائياً).")
                obj.delete() # Delete the component instance

            messages.success(self.request, 'تم تحديث عملية التشطيب بنجاح.')
            return redirect(self.get_success_url())
        return self.form_invalid(form)

    def form_invalid(self, form):
        """
        Catches form validation errors and adds them to the messages framework
        so they can be displayed as toast notifications.
        """
        error_list = []
        for field, errors in form.errors.items():
            if field == '__all__':
                error_list.extend(errors)
            else:
                label = form.fields.get(field).label if form.fields.get(field) else field
                error_list.extend([f"{label}: {error}" for error in errors])
        
        error_string = " ".join(error_list)
        messages.error(self.request, f"فشل الحفظ. الرجاء تصحيح الأخطاء: {error_string}")

        return super().form_invalid(form)

# In production/views.py

class FinishingProcessDetailView(LoginRequiredMixin, DetailView):
    model = FinishingProcess
    template_name = 'production/finishing_detail.html'
    context_object_name = 'finishing_process'

    def get_queryset(self):
        # CORRECTED: The query now follows the correct, deep path to the size_group
        return super().get_queryset().select_related(
            'dyeing_process__assembly_process__production_order__product',
            'dyeing_process__assembly_process__production_order__bom_version__size_group',
            'external_manufacturer', 
            'finisher', 
            'supervisor'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        process = self.get_object()
        context['exit_permit'] = process.exit_permits.first()
        
        if not process.is_completed:
            context['receive_form'] = FinishingReceiveForm(instance=process)

        quantity_input = Decimal(process.quantity_input or 0)
        quantity_output = Decimal(process.quantity_output or 0)
        defects = Decimal(process.defects_in_finishing or 0)
        loss_quantity = quantity_input - quantity_output - defects
        
        efficiency = (quantity_output / quantity_input * 100) if quantity_input > 0 else 0
        defect_rate = (defects / quantity_input * 100) if quantity_input > 0 else 0
        loss_rate = (loss_quantity / quantity_input * 100) if quantity_input > 0 else 0

        context['finishing_stats'] = {
            'efficiency': efficiency,
            'defect_rate': defect_rate,
            'loss_rate': loss_rate,
        }

        if process.finishing_type == 'outsourced' and not context['exit_permit'] and not process.is_completed:
            production_order = process.dyeing_process.assembly_process.production_order
            product = production_order.product
            
            # CORRECTED: Get the size group from the order's specific BOM version
            bom = production_order.bom_version
            size_group = bom.size_group if bom else None

            description_parts = [
                f"منتجات جاهزة للتشطيب للمنتج: {product.name} (أمر #{production_order.order_number})"
            ]
            if size_group:
                sizes_str = ", ".join(size_group.sizes)
                description_parts.append(f"مجموعة المقاسات: {size_group.name} ({sizes_str})")
            
            initial_data = {
                'permit_type': 'finishing_products',
                'items_description': "\n".join(description_parts),
                'quantity': process.quantity_input,
                'destination': process.external_manufacturer.name if process.external_manufacturer else '',
                'purpose': 'إرسال للتشطيب الخارجي',
                'valid_until': timezone.now() + timedelta(days=7)
            }
            context['exit_permit_form'] = ExitPermitForm(initial=initial_data)
        
        return context

class FinishingProcessDeleteView(LoginRequiredMixin, DeleteView):
    model = FinishingProcess
    template_name = 'production/finishing_confirm_delete.html'
    success_url = reverse_lazy('production:finishing_list')
    context_object_name = 'finishing_process'



# Add this new AJAX view to your views.py
# In production/views.py

@login_required
def ajax_get_finishing_bom_components_for_dyeing(request):
    """
    AJAX view to fetch BOM components (excluding fabric) for a given dyeing process,
    along with their available stock in raw material warehouses.
    """
    dyeing_process_id = request.GET.get('dyeing_process_id')
    if not dyeing_process_id:
        return JsonResponse({'error': 'Dyeing Process ID required'}, status=400)

    try:
        dyeing_process = DyeingProcess.objects.select_related(
            'assembly_process__production_order__bom_version'
        ).get(pk=dyeing_process_id)
        
        production_order = dyeing_process.assembly_process.production_order
        bom = production_order.bom_version

        if not bom:
            return JsonResponse({'components': [], 'message': 'لا توجد قائمة مواد (BOM) نشطة للمنتج.'})

        # --- FIX: Changed 'type' to 'warehouse_type' and included both component and textile types ---
        raw_material_warehouses = Warehouse.objects.filter(
            warehouse_type__in=['components', 'textile'], is_active=True
        )
        
        bom_items = bom.items.filter(
            material__is_active=True
        ).exclude(
            material__product_type='fabric'
        ).select_related('material__unit_new').all()
        
        components = []
        for item in bom_items:
            required_quantity_for_finishing = item.quantity * dyeing_process.quantity_received
            
            stock_items = StockItem.objects.filter(
                product=item.material,
                warehouse__in=raw_material_warehouses
            ).select_related('warehouse')

            # --- FIX: Correctly build the warehouses_data list ---
            warehouses_data = [{
                'id': si.warehouse.id,
                'name': si.warehouse.name,
                'available_quantity': si.available_quantity 
            } for si in stock_items]
            
            total_available = stock_items.aggregate(
                total=Coalesce(Sum(F('quantity') - F('reserved_quantity')), Decimal('0.0'))
            )['total']

            components.append({
                'material_id': item.material.id,
                'name': item.material.name,
                'total_required': float(required_quantity_for_finishing),
                'available_stock_total': float(total_available),
                'unit': item.material.unit_new.symbol if item.material.unit_new else 'وحدة',
                'warehouses': warehouses_data,
            })
            
        return JsonResponse({'components': components})

    except DyeingProcess.DoesNotExist:
        return JsonResponse({'error': 'Dyeing Process not found'}, status=404)
    except Exception as e:
        logging.error(f"Error in ajax_get_finishing_bom_components_for_dyeing: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    

@login_required
@require_POST
def receive_finishing_process(request, pk):
    """
    Handles receiving finished goods.
    FIX: Now correctly calculates the cost and adds products to stock.
    """
    finishing_process = get_object_or_404(FinishingProcess, pk=pk, is_completed=False)
    form = FinishingReceiveForm(request.POST, instance=finishing_process)

    if form.is_valid():
        with transaction.atomic():
            process = form.save(commit=False)
            process.is_completed = True
            process.actual_completion_date = timezone.now()
            
            # FIX: Explicit cost calculation
            process.calculate_total_cost() # This method should use ManufacturerProductPrice
            process.save()

            # FINANCIAL LOGIC
            if process.finishing_type == 'outsourced' and process.external_manufacturer and process.total_finishing_cost > 0:
                success = create_invoice_and_transaction(
                    request=request,
                    process_instance=process,
                    manufacturer=process.external_manufacturer,
                    cost=process.total_finishing_cost,
                    expense_name=_("Outsourced Finishing Costs"),
                    notes=_("تكلفة تشطيب: {prod_name} ({qty} قطعة)").format(
                        prod_name=process.dyeing_process.assembly_process.production_order.product.name,
                        qty=process.quantity_output
                    )
                )
                if not success:
                    raise ValueError("Failed to create financial records for finishing.")

            # INVENTORY LOGIC
            production_order = finishing_process.dyeing_process.assembly_process.production_order
            finished_product = production_order.product
            destination_warehouse = finishing_process.destination_warehouse
            quantity_produced = finishing_process.quantity_output

            if quantity_produced > 0:
                if not destination_warehouse:
                    messages.error(request, _("Cannot complete: A destination warehouse was not selected."))
                    raise ValueError("Destination warehouse is missing.")

                stock_item, created = StockItem.objects.get_or_create(
                    product=finished_product,
                    warehouse=destination_warehouse,
                    defaults={'quantity': 0}
                )

                ProductBatch.objects.create(
                    stock=stock_item,
                    batch_number=production_order.batch_number,
                    quantity=quantity_produced,
                    production_finishing_source=finishing_process,
                    cost_per_piece=production_order.cost_analysis.cost_per_piece if hasattr(production_order, 'cost_analysis') else 0
                )

                StockMovement.objects.create(
                    stock_item=stock_item,
                    movement_type='in',
                    quantity=quantity_produced,
                    reference_number=f"PROD-{production_order.order_number}",
                    notes=_("Completed production from order #{num}").format(num=production_order.order_number),
                    created_by=request.user
                )
                messages.info(request, _("{qty} pieces of '{prod}' added to warehouse '{wh}'.").format(
                    qty=quantity_produced, prod=finished_product.name, wh=destination_warehouse.name
                ))

            production_order.status = 'completed'
            production_order.actual_completion_date = timezone.now().date()
            production_order.save(update_fields=['status', 'actual_completion_date'])
            messages.success(request, _("Finishing process for order {order_num} has been completed.").format(
                order_num=production_order.order_number
            ))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{form.fields[field].label if field != '__all__' else 'Error'}: {error}")

    return redirect('production:finishing_detail', pk=pk)


@login_required
def ajax_get_order_count_for_period(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if not start_date_str or not end_date_str:
        return JsonResponse({'error': 'Start and end dates are required.'}, status=400)

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        count = ProductionOrder.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).count()

        return JsonResponse({'success': True, 'count': count})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format.'}, status=400)

@login_required
def print_finishing_process_pdf(request, pk):
    process = get_object_or_404(FinishingProcess, pk=pk)
    context = {'finishing_process': process, 'timestamp': timezone.now()}
    html_string = render_to_string('pdf/production/finishing_process_pdf.html', context)
    
    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config)
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Finishing_Process_{pk}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:finishing_detail', pk=pk)



# ... (Other views remain unchanged)

@login_required
def ajax_get_finishing_costs(request):
    """
    AJAX view to calculate and return finishing costs based on the dyeing process.
    This includes BOM component costs and external manufacturer costs if applicable.
    """
    dyeing_process_id = request.GET.get('dyeing_process_id')
    
    if not dyeing_process_id:
        return JsonResponse({'success': False, 'error': 'Dyeing process ID is required.'}, status=400)

    try:
        dyeing_process = DyeingProcess.objects.select_related(
            'assembly_process__production_order__bom_version'
        ).get(pk=dyeing_process_id)
        
        production_order = dyeing_process.assembly_process.production_order
        bom = production_order.bom_version
        quantity_input = dyeing_process.quantity_received # The quantity to be finished

        total_bom_cost = Decimal('0.00')
        components_breakdown = []

        if bom:
            # Sum the cost of all BOM items (excluding fabric)
            # This assumes BOM items have a 'cost' property or can calculate it.
            # We'll filter for non-fabric items as finishing uses accessories.
            for item in bom.items.exclude(material__product_type='fabric').select_related('material'):
                item_cost = item.quantity * item.material.cost_price * quantity_input
                total_bom_cost += item_cost
                components_breakdown.append({
                    'name': item.material.name,
                    'cost': float(item_cost) # Convert to float for JSON serialization
                })

        # The external manufacturer cost will be calculated on the frontend
        # based on the selected manufacturer and the quantity_input.
        # We just need to provide the quantity_input here.

        return JsonResponse({
            'success': True,
            'total_bom_cost': float(total_bom_cost),
            'components': components_breakdown,
            'quantity_input': float(quantity_input) # Pass the quantity to the frontend
        })

    except DyeingProcess.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Dyeing process not found.'}, status=404)
    except Exception as e:
        logging.error(f"Error in ajax_get_finishing_costs: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
# External Manufacturer Views (continued)
class ExternalManufacturerListView(LoginRequiredMixin, ListView):
    model = ExternalManufacturer
    template_name = 'production/manufacturer/manufacturer_list.html'
    context_object_name = 'manufacturers'
    paginate_by = 15

    def get_queryset(self):
        queryset = ExternalManufacturer.objects.all()
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query)
            )
        return queryset.order_by('name')

class ExternalManufacturerDetailView(LoginRequiredMixin, DetailView):
    """
    Displays the details for a single external manufacturer, including their
    job history, financial status, and performance metrics.
    """
    model = ExternalManufacturer
    template_name = 'production/manufacturer/manufacturer_detail.html'
    context_object_name = 'manufacturer'

    def get_queryset(self):
        """
        Pre-fetches related data for efficiency to avoid numerous database queries
        in the template and context data processing.
        """
        return super().get_queryset().select_related('finance_account').prefetch_related(
            # Prefetching deep relationships to get all necessary data in fewer queries
            'assembly_processes__production_order__product',
            'dyeing_jobs__assembly_process__production_order__product',
            'finishing_jobs__dyeing_process__assembly_process__production_order__product',
            'product_prices__product'
        )

    def get_context_data(self, **kwargs):
        """
        Gathers and processes all data needed for the manufacturer detail page.
        This method now standardizes both active jobs and job history.
        """
        context = super().get_context_data(**kwargs)
        manufacturer = self.get_object()
        
        # --- Combine all job types into a single list ---
        assembly_jobs = manufacturer.assembly_processes.all()
        dyeing_jobs = manufacturer.dyeing_jobs.all()
        finishing_jobs = manufacturer.finishing_jobs.all()
        all_jobs = list(chain(assembly_jobs, dyeing_jobs, finishing_jobs))

        active_jobs_raw = [job for job in all_jobs if not job.is_completed]
        completed_jobs_raw = [job for job in all_jobs if job.is_completed]
        default_date = timezone.now()

        # --- FIX: Standardize the Active Jobs list ---
        active_jobs_list = []
        for job in active_jobs_raw:
            production_order = None
            job_type_display = "غير محدد"
            start_date = None
            detail_url = "#"

            if isinstance(job, AssemblyProcess):
                production_order = job.production_order
                job_type_display = "تجميع"
                start_date = job.start_date
                detail_url = reverse('production:assembly_detail', kwargs={'pk': job.pk})
            elif isinstance(job, DyeingProcess):
                production_order = job.assembly_process.production_order
                job_type_display = "صباغة"
                start_date = job.sent_date
                detail_url = reverse('production:dyeing_detail', kwargs={'pk': job.pk})
            elif isinstance(job, FinishingProcess):
                production_order = job.dyeing_process.assembly_process.production_order
                job_type_display = "تشطيب"
                start_date = job.start_date
                detail_url = reverse('production:finishing_detail', kwargs={'pk': job.pk})

            if production_order:
                active_jobs_list.append({
                    'job_object': job, # Pass original object for filters like 'class_name'
                    'order': production_order,
                    'job_type': job_type_display,
                    'start_date': start_date,
                    'detail_url': detail_url,
                })
        context['active_jobs'] = sorted(active_jobs_list, key=lambda x: x['start_date'] or default_date, reverse=True)

        # --- Standardize the Job History list ---
        job_history_list = []
        for job in completed_jobs_raw:
            cost, completion_date, detail_url, production_order, job_type_display = 0, None, "#", None, "غير محدد"
            if isinstance(job, AssemblyProcess):
                cost, completion_date, production_order, job_type_display, detail_url = job.assembly_cost, job.actual_completion_date, job.production_order, "تجميع", reverse('production:assembly_detail', kwargs={'pk': job.pk})
            elif isinstance(job, DyeingProcess):
                cost, completion_date, production_order, job_type_display, detail_url = job.total_dyeing_cost, job.actual_return_date, job.assembly_process.production_order, "صباغة", reverse('production:dyeing_detail', kwargs={'pk': job.pk})
            elif isinstance(job, FinishingProcess):
                cost, completion_date, production_order, job_type_display, detail_url = job.total_finishing_cost, job.actual_completion_date, job.dyeing_process.assembly_process.production_order, "تشطيب", reverse('production:finishing_detail', kwargs={'pk': job.pk})

            if production_order:
                job_history_list.append({'order_number': production_order.order_number, 'product_name': production_order.product.name, 'cost': cost or 0, 'completion_date': completion_date, 'job_type': job_type_display, 'detail_url': detail_url})
        
        context['job_history'] = sorted(job_history_list, key=lambda x: x['completion_date'] or default_date, reverse=True)
        
        # --- Calculate summary metrics ---
        context['product_prices'] = manufacturer.product_prices.all()
        context['total_value_of_completed_jobs'] = sum(item['cost'] for item in job_history_list)
        context['total_pieces_completed'] = sum(getattr(job, 'quantity_received', getattr(job, 'quantity_output', 0)) or 0 for job in completed_jobs_raw)
        
        # This is an estimate as active jobs may not have a final cost yet.
        context['total_value_of_active_jobs'] = sum(
            getattr(job, 'assembly_cost', 0) or 0 + 
            getattr(job, 'total_dyeing_cost', 0) or 0 + 
            getattr(job, 'total_finishing_cost', 0) or 0 
            for job in active_jobs_raw
        )

        return context



class ExternalManufacturerCreateView(LoginRequiredMixin, CreateView):
    model = ExternalManufacturer
    form_class = ExternalManufacturerForm
    template_name = 'production/manufacturer/manufacturer_form.html'
    success_url = reverse_lazy('production:manufacturers:manufacturer_list')

    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة المصنع الخارجي بنجاح.')
        return super().form_valid(form)

class ExternalManufacturerUpdateView(LoginRequiredMixin, UpdateView):
    model = ExternalManufacturer
    form_class = ExternalManufacturerForm
    template_name = 'production/manufacturer/manufacturer_form.html'
    
    def get_success_url(self):
        return reverse_lazy('production:manufacturers:manufacturer_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            if self.request.POST:
                context['product_price_formset'] = ManufacturerProductPriceFormSet(self.request.POST, instance=self.object, prefix='prices')
            else:
                context['product_price_formset'] = ManufacturerProductPriceFormSet(instance=self.object, prefix='prices')
            return context

    # ADDED: Method to validate and save formset
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['product_price_formset']
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
            messages.success(self.request, 'تم تحديث بيانات المصنع والأسعار بنجاح.')
            return redirect(self.get_success_url())
        else:
            # Add formset errors to messages if invalid
            for fs_form in formset:
                for field, error_list in fs_form.errors.items():
                    for error in error_list:
                         messages.error(self.request, f"خطأ في الأسعار: {error}")
            return self.form_invalid(form)



class ExitPermitListView(LoginRequiredMixin, ListView):
    model = ExitPermit
    template_name = 'production/exit_permit/exit_permit_list.html'
    context_object_name = 'permits'
    paginate_by = 15

    def get_queryset(self):
        queryset = ExitPermit.objects.select_related('production_order', 'requested_by', 'approved_by')
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by('-requested_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = ExitPermit.STATUS_CHOICES
        return context

class ExitPermitDetailView(LoginRequiredMixin, DetailView):
    model = ExitPermit
    template_name = 'production/exit_permit/exit_permit_detail.html'
    context_object_name = 'permit'

class ExitPermitCreateView(LoginRequiredMixin, CreateView):
    model = ExitPermit
    form_class = ExitPermitForm
    template_name = 'production/exit_permit/exit_permit_form.html'
    
    def get_initial(self):
        """Pre-populates the form with data from the related assembly process."""
        initial = super().get_initial()
        assembly_id = self.request.GET.get('assembly_id')
        if assembly_id:
            try:
                assembly_process = AssemblyProcess.objects.select_related('production_order', 'external_manufacturer').get(pk=assembly_id)
                initial['production_order'] = assembly_process.production_order
                initial['permit_type'] = 'assembly_pieces'
                initial['items_description'] = f"قطع مجمعة للمنتج: {assembly_process.production_order.product.name}"
                initial['quantity'] = assembly_process.quantity_sent
                if assembly_process.external_manufacturer:
                    initial['destination'] = f"مصنع: {assembly_process.external_manufacturer.name}"
                initial['purpose'] = "إرسال للتجميع الخارجي"
            except AssemblyProcess.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        """Links the new permit to the assembly process and sets the user."""
        # Check for assembly_id in POST data from the modal form
        assembly_id = self.request.POST.get('assembly_id')
        if assembly_id:
            try:
                form.instance.assembly_process = get_object_or_404(AssemblyProcess, pk=assembly_id)
            except AssemblyProcess.DoesNotExist:
                pass  # Should not happen if the request is valid
        
        form.instance.requested_by = self.request.user
        messages.success(self.request, "تم إنشاء طلب تصريح خروج جديد بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the detail page of the newly created permit.
        This provides immediate confirmation to the user.
        """
        return reverse('production:exit_permits:exit_permit_detail', kwargs={'pk': self.object.pk})


# In production/views.py

@login_required
@require_POST
def create_exit_permit_ajax(request):
    """
    Handles the creation of an exit permit via AJAX for any production stage.
    This single, robust function correctly handles assembly, dyeing, and finishing.
    """
    # Create a mutable copy of the POST data so we can add the production_order to it.
    mutable_data = request.POST.copy()

    assembly_id = mutable_data.get('assembly_id')
    dyeing_id = mutable_data.get('dyeing_id')
    finishing_id = mutable_data.get('finishing_id')

    if not any([assembly_id, dyeing_id, finishing_id]):
        return JsonResponse({'success': False, 'error': 'Process ID is missing.'}, status=400)
    
    # --- Step 1: Find the correct Production Order BEFORE validation ---
    production_order = None
    try:
        if finishing_id:
            process = get_object_or_404(FinishingProcess, pk=finishing_id)
            production_order = process.dyeing_process.assembly_process.production_order
        elif dyeing_id:
            process = get_object_or_404(DyeingProcess, pk=dyeing_id)
            production_order = process.assembly_process.production_order
        elif assembly_id:
            process = get_object_or_404(AssemblyProcess, pk=assembly_id)
            production_order = process.production_order
    except Exception as e:
         return JsonResponse({'success': False, 'error': f'Could not find the related process: {e}'}, status=404)

    # --- Step 2: Add the Production Order to the form data ---
    if production_order:
        mutable_data['production_order'] = production_order.pk
    
    # --- Step 3: Validate the form WITH the complete data ---
    form = ExitPermitForm(mutable_data)

    if form.is_valid():
        with transaction.atomic():
            permit = form.save(commit=False)
            
            # Link the specific process object to the permit
            if finishing_id:
                permit.finishing_process = get_object_or_404(FinishingProcess, pk=finishing_id)
            elif dyeing_id:
                permit.dyeing_process = get_object_or_404(DyeingProcess, pk=dyeing_id)
            elif assembly_id:
                permit.assembly_process = get_object_or_404(AssemblyProcess, pk=assembly_id)

            permit.requested_by = request.user
            permit.save()
            
            # Return a success message in the JSON response for the frontend to display
            return JsonResponse({
                'success': True, 
                'message': f"تم إنشاء تصريح الخروج {permit.permit_number} بنجاح."
            })
    else:
        # If the form is invalid, return the specific errors for easier debugging.
        return JsonResponse({
            'success': False, 
            'error': 'فشل الإنشاء، يرجى مراجعة الأخطاء.', 
            'errors': form.errors
        }, status=400)
@login_required
def print_dyeing_process_pdf(request, pk):
    dyeing_process = get_object_or_404(DyeingProcess.objects.select_related(
        'assembly_process__production_order__product', 'dyeing_facility'
    ), pk=pk)
    
    exit_permit = dyeing_process.exit_permits.first()

    context = {
        'dyeing_process': dyeing_process,
        'exit_permit': exit_permit,
        'timestamp': timezone.now()
    }
    
    # Render PDF template to an HTML string
    html_string = render_to_string('pdf/production/dyeing_process_pdf.html', context)
    
    options = {
        'page-size': 'A4', 'margin-top': '0.75in', 'margin-right': '0.75in',
        'margin-bottom': '0.75in', 'margin-left': '0.75in', 'encoding': "UTF-8",
        '--header-font-name': 'Tajawal', '--footer-font-name': 'Tajawal',
        '--load-error-handling': 'ignore', '--load-media-error-handling': 'ignore',
    }

    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options=options)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Dyeing_Process_{dyeing_process.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:dyeing_detail', pk=pk)


@login_required
def print_assembly_detail_pdf(request, pk):
    """
    Exports the Assembly Process detail page to a PDF file using wkhtmltopdf.
    """
    assembly_process = get_object_or_404(AssemblyProcess.objects.select_related(
        'production_order__product', 'external_manufacturer', 'assembler'
    ), pk=pk)
    
    # Pre-fetch the related exit permit
    exit_permit = assembly_process.exit_permits.first()

    context = {
        'assembly_process': assembly_process,
        'exit_permit': exit_permit, # Pass the permit to the context
        'timestamp': timezone.now()
    }
    
    # Render the PDF template to an HTML string
    html_string = render_to_string('pdf/production/assembly_detail_pdf.html', context)
    
    # Configure PDF options
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        '--header-font-name': 'Tajawal',
        '--footer-font-name': 'Tajawal',
        '--load-error-handling': 'ignore',
        '--load-media-error-handling': 'ignore',
    }

    try:
        # Ensure WKHTMLTOPDF_PATH is configured in settings.py
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options=options)
        
        # Create HTTP response
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Assembly_Process_{assembly_process.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        # 'inline' opens it in the browser, 'attachment' forces download
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:assembly_detail', pk=pk)


class ExternalManufacturerDeleteView(LoginRequiredMixin, DeleteView):
    model = ExternalManufacturer
    template_name = 'production/manufacturer/manufacturer_confirm_delete.html'
    success_url = reverse_lazy('production:manufacturers:manufacturer_list')

    def form_valid(self, form):
        # Add a success message upon deletion
        messages.success(self.request, f"تم حذف المصنع '{self.object.name}' بنجاح.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # This is the phrase the user must type to confirm deletion.
        context['confirmation_phrase'] = 'انا اوافق علي مسح هذا المصنع'
        return context

@login_required
@require_POST
def approve_exit_permit(request, pk):
    permit = get_object_or_404(ExitPermit, pk=pk)
    if permit.is_approvable:
        permit.status = 'approved'
        permit.approved_by = request.user
        permit.approved_at = timezone.now()
        permit.save()
        messages.success(request, f"تمت الموافقة على تصريح الخروج رقم {permit.permit_number}.")
    else:
        messages.error(request, "لا يمكن الموافقة على هذا التصريح في حالته الحالية.")
    return redirect('production:exit_permits:exit_permit_detail', pk=permit.pk)

@login_required
@require_POST
def use_exit_permit(request, pk):
    permit = get_object_or_404(ExitPermit, pk=pk)
    if permit.is_usable:
        permit.status = 'used'
        permit.used_at = timezone.now()
        permit.save()
        messages.success(request, f"تم تسجيل استخدام التصريح رقم {permit.permit_number}.")
    else:
        messages.error(request, "لا يمكن استخدام هذا التصريح (قد يكون غير معتمد أو منتهي الصلاحية).")
    return redirect('production:exit_permits:exit_permit_detail', pk=permit.pk)

# PDF View for a single Exit Permit
@login_required
def print_exit_permit_pdf(request, pk):
    permit = get_object_or_404(ExitPermit, pk=pk)
    context = {
        'permit': permit,
        'timestamp': timezone.now()
    }
    html_string = render_to_string('pdf/production/exit_permit_pdf.html', context)
    
    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8", 'page-size': 'A4',
        })
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="ExitPermit_{permit.permit_number}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:exit_permit_detail', pk=pk)


@login_required
def print_exit_permit_receipt_pdf(request, pk):
    receipt = get_object_or_404(ReceiptConfirmation.objects.select_related('exit_permit'), pk=pk)
    context = {
        'receipt': receipt,
        'timestamp': timezone.now()
    }
    html_string = render_to_string('pdf/production/exit_permit_receipt_pdf.html', context)
    
    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8", 'page-size': 'A4',
        })
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Receipt_{receipt.exit_permit.permit_number}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:exit_permits:exit_permit_detail', pk=receipt.exit_permit.pk)


class ExitPermitReceiptView(LoginRequiredMixin, CreateView):
    # ... (view content remains the same) ...
    model = ReceiptConfirmation
    form_class = ReceiptConfirmationForm
    template_name = 'production/exit_permit/exit_permit_receipt.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        permit = get_object_or_404(ExitPermit, pk=self.kwargs['pk'])
        context['permit'] = permit
        
        # If a receipt already exists, pass it to the context to display its details
        if hasattr(permit, 'receipt_confirmation'):
            context['receipt'] = permit.receipt_confirmation
        return context

    def get_form_kwargs(self):
        """Passes the permit instance to the form for validation."""
        kwargs = super().get_form_kwargs()
        kwargs['permit'] = get_object_or_404(ExitPermit, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        permit = get_object_or_404(ExitPermit, pk=self.kwargs['pk'])

        # Prevent creating a new receipt if one already exists
        if hasattr(permit, 'receipt_confirmation'):
            messages.error(self.request, 'تم تسجيل إيصال استلام لهذا التصريح بالفعل.')
            return redirect('production:exit_permits:exit_permit_detail', pk=permit.pk)

        # Ensure the permit has been marked as 'used' before confirming receipt
        if permit.status != 'used':
             messages.error(self.request, 'لا يمكن تأكيد استلام هذا التصريح. يجب أن يكون في حالة "مستخدم" أولاً.')
             return redirect('production:exit_permits:exit_permit_detail', pk=permit.pk)

        form.instance.exit_permit = permit
        form.instance.confirmed_by = self.request.user
        
        # The form is valid, so we can now save the object.
        self.object = form.save()
        
        messages.success(self.request, 'تم تأكيد استلام التصريح بنجاح.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        # Redirect back to the permit detail page after successful submission
        return reverse_lazy('production:exit_permits:exit_permit_detail', kwargs={'pk': self.kwargs['pk']})

# Quality Control Views



from .forms import QualityControlCheckForm

# =============================================================================
#  NEW: Quality Control Views
# =============================================================================

class QualityControlListView(LoginRequiredMixin, ListView):
    model = QualityControlCheck
    template_name = 'production/quality/quality_list.html'
    context_object_name = 'quality_checks'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = QualityControlCheck.objects.select_related(
            'production_order', 'inspector', 'approved_by'
        ).order_by('-check_date')
        
        # Filtering logic
        check_type = self.request.GET.get('check_type')
        if check_type:
            queryset = queryset.filter(check_type=check_type)
        
        grade = self.request.GET.get('grade')
        if grade:
            queryset = queryset.filter(overall_grade=grade)
        
        approved = self.request.GET.get('approved')
        if approved == 'true':
            queryset = queryset.filter(approved=True)
        elif approved == 'false':
            queryset = queryset.filter(approved=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "مراقبة الجودة"
        context['check_types'] = QualityControlCheck.CHECK_TYPES
        context['quality_grades'] = QualityControlCheck.QUALITY_GRADES
        # Pass filter values to template for display
        context['check_type_filter'] = self.request.GET.get('check_type', '')
        context['grade_filter'] = self.request.GET.get('grade', '')
        context['approved_filter'] = self.request.GET.get('approved', '')
        return context

class QualityControlDetailView(LoginRequiredMixin, DetailView):
    model = QualityControlCheck
    template_name = 'production/quality/quality_detail.html'
    context_object_name = 'quality_check'

class QualityControlCreateView(LoginRequiredMixin, CreateView):
    model = QualityControlCheck
    form_class = QualityControlCheckForm
    template_name = 'production/quality/quality_form.html'
    
    def get_initial(self):
        """Pre-populates the form based on the process it's linked from."""
        initial = super().get_initial()
        process = None
        
        if 'cutting_id' in self.request.GET:
            process = get_object_or_404(CuttingProcess, pk=self.request.GET['cutting_id'])
            initial['check_type'] = 'cutting_quality'
            initial['items_checked'] = process.total_pieces_cut
        elif 'assembly_id' in self.request.GET:
            process = get_object_or_404(AssemblyProcess, pk=self.request.GET['assembly_id'])
            initial['check_type'] = 'assembly_quality'
            initial['items_checked'] = process.quantity_received
        elif 'dyeing_id' in self.request.GET:
            process = get_object_or_404(DyeingProcess, pk=self.request.GET['dyeing_id'])
            initial['check_type'] = 'dyeing_quality'
            initial['items_checked'] = process.quantity_received
        elif 'finishing_id' in self.request.GET:
            process = get_object_or_404(FinishingProcess, pk=self.request.GET['finishing_id'])
            initial['check_type'] = 'finishing_quality'
            initial['items_checked'] = process.quantity_output

        if process:
            initial['production_order'] = process.production_order if hasattr(process, 'production_order') else process.assembly_process.production_order

        return initial

    def form_valid(self, form):
        form.instance.inspector = self.request.user
        
        # Link the check to the specific process
        if 'cutting_id' in self.request.GET:
            process = get_object_or_404(CuttingProcess, pk=self.request.GET['cutting_id'])
            form.instance.cutting_process = process
            form.instance.production_order = process.production_order
        elif 'assembly_id' in self.request.GET:
            process = get_object_or_404(AssemblyProcess, pk=self.request.GET['assembly_id'])
            form.instance.assembly_process = process
            form.instance.production_order = process.production_order
        elif 'dyeing_id' in self.request.GET:
            process = get_object_or_404(DyeingProcess, pk=self.request.GET['dyeing_id'])
            form.instance.dyeing_process = process
            form.instance.production_order = process.assembly_process.production_order
        elif 'finishing_id' in self.request.GET:
            process = get_object_or_404(FinishingProcess, pk=self.request.GET['finishing_id'])
            form.instance.finishing_process = process
            form.instance.production_order = process.dyeing_process.assembly_process.production_order
        
        messages.success(self.request, 'تم إنشاء فحص الجودة بنجاح.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('production:quality:quality_detail', kwargs={'pk': self.object.pk})

class QualityControlUpdateView(LoginRequiredMixin, UpdateView):
    model = QualityControlCheck
    form_class = QualityControlCheckForm
    template_name = 'production/quality/quality_form.html'

    def get_success_url(self):
        return reverse('production:quality:quality_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث فحص الجودة بنجاح.')
        return super().form_valid(form)

class QualityControlDeleteView(LoginRequiredMixin, DeleteView):
    model = QualityControlCheck
    template_name = 'production/quality/quality_confirm_delete.html'
    success_url = reverse_lazy('production:quality:quality_list')

    def form_valid(self, form):
        messages.success(self.request, f"تم حذف فحص الجودة بنجاح.")
        return super().form_valid(form)

@login_required
@require_POST
def approve_quality_check(request, pk):
    quality_check = get_object_or_404(QualityControlCheck, pk=pk)
    
    if not quality_check.approved:
        quality_check.approved = True
        quality_check.approved_by = request.user
        quality_check.save()
        messages.success(request, f'تم اعتماد فحص الجودة.')
    else:
        messages.info(request, 'فحص الجودة معتمد بالفعل.')
    
    return redirect('production:quality:quality_detail', pk=pk)

# Production Report Views
class ProductionReportListView(LoginRequiredMixin, ListView):
    model = ProductionReport
    template_name = 'production/report_list.html'
    context_object_name = 'reports'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = ProductionReport.objects.select_related('generated_by').order_by('-generated_at')
        
        # تصفية حسب نوع التقرير
        report_type = self.request.GET.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_types'] = ProductionReport.REPORT_TYPES
        context['report_type_filter'] = self.request.GET.get('report_type', '')
        return context

class ProductionReportCreateView(LoginRequiredMixin, CreateView):
    model = ProductionReport
    template_name = 'production/report_form.html'
    fields = ['report_type', 'title', 'period_start', 'period_end', 'report_content', 'recommendations']
    success_url = reverse_lazy('production:report_list')
    
    def form_valid(self, form):
        form.instance.generated_by = self.request.user
        
        # حساب الإحصائيات تلقائياً
        period_start = form.cleaned_data['period_start']
        period_end = form.cleaned_data['period_end']
        
        orders_in_period = ProductionOrder.objects.filter(
            created_at__date__range=[period_start, period_end]
        )
        
        form.instance.total_orders = orders_in_period.count()
        form.instance.completed_orders = orders_in_period.filter(status='completed').count()
        form.instance.total_pieces_produced = orders_in_period.filter(
            status='completed'
        ).aggregate(total=Sum('quantity_ordered'))['total'] or 0
        
        # حساب متوسط نقاط الجودة
        quality_checks = QualityControlCheck.objects.filter(
            check_date__date__range=[period_start, period_end]
        )
        if quality_checks.exists():
            grade_mapping = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
            total_score = sum(grade_mapping.get(check.overall_grade, 0) for check in quality_checks)
            form.instance.average_quality_score = total_score / quality_checks.count()
        
        messages.success(self.request, 'تم إنشاء التقرير بنجاح.')
        return super().form_valid(form)

class ProductionReportDetailView(LoginRequiredMixin, DetailView):
    model = ProductionReport
    template_name = 'production/report_detail.html'
    context_object_name = 'report'

# Cost Analysis Views
class CostAnalysisListView(LoginRequiredMixin, ListView):
    model = ProductionCostAnalysis
    template_name = 'production/cost_analysis_list.html'
    context_object_name = 'cost_analyses'
    paginate_by = 20
    
    def get_queryset(self):
        return ProductionCostAnalysis.objects.select_related(
            'production_order', 'production_order__product', 'analyzed_by'
        ).order_by('-analysis_date')


class CostAnalysisSelectOrderView(LoginRequiredMixin, ListView):
    """
    Displays a list of completed production orders that do not yet have a
    cost analysis, allowing the user to select one to analyze.
    """
    model = ProductionOrder
    template_name = 'production/cost_analysis_select_order.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        # Show only completed orders that don't have a cost analysis yet
        return ProductionOrder.objects.filter(
            status='completed',
            cost_analysis__isnull=True
        ).select_related('product').order_by('-actual_completion_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "اختر أمر إنتاج لتحليل التكلفة"
        return context

class CostAnalysisCreateView(LoginRequiredMixin, View):
    """
    This view handles the creation of a ProductionCostAnalysis object.
    It automatically calculates costs from related processes.
    """
    def get(self, request, *args, **kwargs):
        order_id = self.kwargs.get('order_id')
        order = get_object_or_404(ProductionOrder, pk=order_id)

        # Check if an analysis already exists
        if hasattr(order, 'cost_analysis'):
            messages.info(request, f"تحليل التكلفة لأمر الإنتاج {order.order_number} موجود بالفعل.")
            return redirect('production:cost_analysis_detail', pk=order.cost_analysis.pk)

        try:
            with transaction.atomic():
                # --- Calculate Costs from Production Stages ---
                
                # 1. Fabric Cost
                fabric_cost = order.fabric_meters_allocated * order.textile_stock.product.cost_price
                
                # 2. Assembly, Dyeing, and Finishing Costs
                # Sum costs from all related processes
                assembly_cost = order.assembly_processes.aggregate(total=Sum('assembly_cost'))['total'] or Decimal('0.0')
                dyeing_cost = DyeingProcess.objects.filter(assembly_process__production_order=order).aggregate(total=Sum('total_dyeing_cost'))['total'] or Decimal('0.0')
                finishing_cost = FinishingProcess.objects.filter(dyeing_process__assembly_process__production_order=order).aggregate(total=Sum('total_finishing_cost'))['total'] or Decimal('0.0')

                # Create the analysis instance
                analysis = ProductionCostAnalysis(
                    production_order=order,
                    fabric_cost=fabric_cost,
                    assembly_cost=assembly_cost,
                    dyeing_cost=dyeing_cost,
                    finishing_cost=finishing_cost,
                    # Placeholder for other costs - can be updated later
                    thread_cost=Decimal('0.0'),
                    accessories_cost=Decimal('0.0'),
                    cutting_cost=Decimal('0.0'),
                    transportation_cost=Decimal('0.0'),
                    overhead_cost=Decimal('0.0'),
                    quality_control_cost=Decimal('0.0'),
                    analyzed_by=request.user,
                )
                
                # Calculate totals and save
                analysis.calculate_totals()
                
                messages.success(request, f"تم إنشاء تحليل التكلفة لأمر الإنتاج {order.order_number} بنجاح.")
                return redirect('production:cost_analysis_detail', pk=analysis.pk)

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء حساب التكاليف: {e}")
            return redirect('production:cost_analysis_select_order')
        
class CostAnalysisDetailView(LoginRequiredMixin, DetailView):
    model = ProductionCostAnalysis
    template_name = 'production/cost_analysis_detail.html'
    context_object_name = 'cost_analysis'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cost_analysis = self.get_object()
        order = cost_analysis.production_order
        bom = order.bom_version
        cutting_process = getattr(order, 'cutting_process', None)

        # --- Process Timeline & Durations ---
        timeline = []
        if cutting_process and cutting_process.cutting_date and cutting_process.completed_at:
            duration = cutting_process.completed_at - cutting_process.cutting_date
            timeline.append({
                'stage': 'القص',
                'start': cutting_process.cutting_date,
                'end': cutting_process.completed_at,
                'duration': duration,
                'handler': cutting_process.cutter.get_full_name() if cutting_process.cutter else 'داخلي',
                'cost_per_piece': None
            })

        for assembly in order.assembly_processes.all():
            duration = (assembly.actual_completion_date - assembly.start_date) if assembly.start_date and assembly.actual_completion_date else None
            handler = assembly.external_manufacturer.name if assembly.assembly_type == 'outsourced' and assembly.external_manufacturer else (assembly.assembler.get_full_name() if assembly.assembler else 'داخلي')
            cost_per_piece = assembly.external_manufacturer.price_per_piece if assembly.assembly_type == 'outsourced' and assembly.external_manufacturer else None
            timeline.append({
                'stage': f'التجميع ({assembly.get_assembly_type_display()})',
                'start': assembly.start_date,
                'end': assembly.actual_completion_date,
                'duration': duration,
                'handler': handler,
                'cost_per_piece': cost_per_piece
            })

            for dyeing in assembly.dyeing_processes.all():
                duration = (dyeing.actual_return_date - dyeing.sent_date) if dyeing.sent_date and dyeing.actual_return_date else None
                handler = dyeing.dyeing_facility.name if dyeing.dyeing_facility else 'غير محدد'
                cost_per_piece = dyeing.dyeing_cost_per_piece
                timeline.append({
                    'stage': f'الصباغة ({dyeing.color_specification})',
                    'start': dyeing.sent_date,
                    'end': dyeing.actual_return_date,
                    'duration': duration,
                    'handler': handler,
                    'cost_per_piece': cost_per_piece
                })
                if finishing_process := getattr(dyeing, 'finishing_process', None):
                    duration = (finishing_process.actual_completion_date - finishing_process.start_date) if finishing_process.start_date and finishing_process.actual_completion_date else None
                    handler = finishing_process.external_manufacturer.name if finishing_process.finishing_type == 'outsourced' and finishing_process.external_manufacturer else (finishing_process.finisher.get_full_name() if finishing_process.finisher else 'داخلي')
                    cost_per_piece = finishing_process.external_manufacturer.price_per_piece if finishing_process.finishing_type == 'outsourced' and finishing_process.external_manufacturer else None
                    timeline.append({
                        'stage': 'التشطيب',
                        'start': finishing_process.start_date,
                        'end': finishing_process.actual_completion_date,
                        'duration': duration,
                        'handler': handler,
                        'cost_per_piece': cost_per_piece
                    })
        
        context['timeline'] = timeline

        # --- BOM vs Actual Usage ---
        bom_comparison = []
        if bom:
            bom_materials = {item.material_id: item for item in bom.items.all()}
            actual_assembly = {c.material_id: c.quantity_sent for c in AssemblyComponent.objects.filter(assembly_process__production_order=order)}
            actual_finishing = {c.material_id: c.quantity_sent for c in FinishingComponent.objects.filter(finishing_process__dyeing_process__assembly_process__production_order=order)}
            actual_materials = actual_assembly
            for mat_id, qty in actual_finishing.items():
                actual_materials[mat_id] = actual_materials.get(mat_id, 0) + qty
            all_material_ids = set(bom_materials.keys()) | set(actual_materials.keys())
            for mat_id in all_material_ids:
                bom_item = bom_materials.get(mat_id)
                actual_qty = actual_materials.get(mat_id, Decimal('0.0'))
                material_obj = bom_item.material if bom_item else (Product.objects.get(id=mat_id))
                bom_qty_per_piece = bom_item.quantity if bom_item else Decimal('0.0')
                bom_total_qty = bom_qty_per_piece * order.quantity_ordered
                bom_comparison.append({
                    'material': material_obj.name,
                    'bom_quantity': bom_total_qty,
                    'actual_quantity': actual_qty,
                    'variance': actual_qty - bom_total_qty
                })
        
        context['bom_comparison'] = bom_comparison

        # --- Batch Data Widget Information (Corrected Logic) ---
        batch_data = {
            'order': order,
            'cutting_process': cutting_process,
            'colors': list(set(DyeingProcess.objects.filter(assembly_process__production_order=order).values_list('color_specification', flat=True))),
            # --- FIX: Query ProductBatch for storage locations ---
            'storage_locations': list(set(ProductBatch.objects.filter(
                stock__product=order.product, 
                batch_number=order.batch_number
            ).values_list('stock__warehouse__name', flat=True)))
        }
        
        # --- FIX: Correctly reference the product on the stock item ---
        fabric_bom_quantity = None
        if bom and order.textile_stock:
            try:
                # The material is the product associated with the stock item
                fabric_material = order.textile_stock.product
                fabric_bom_item = BOMItem.objects.get(bom=bom, material=fabric_material)
                fabric_bom_quantity = fabric_bom_item.quantity
            except BOMItem.DoesNotExist:
                fabric_bom_quantity = None
                
        batch_data['fabric_bom_quantity'] = fabric_bom_quantity
        batch_data['fabric_cutting_quantity'] = cutting_process.single_layer_meterage if cutting_process else None

        context['batch_data'] = batch_data
        
        return context

class CostAnalysisUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductionCostAnalysis
    # Use the new, more specific form for editing
    form_class = ProductionCostAnalysisUpdateForm
    template_name = 'production/cost_analysis_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"تعديل تحليل التكلفة لأمر: {self.object.production_order.order_number}"
        return context

    def form_valid(self, form):
        # Recalculate totals after updating fields
        analysis = form.save(commit=False)
        analysis.calculate_totals()
        messages.success(self.request, 'تم تحديث تحليل التكلفة بنجاح.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('production:cost_analysis_detail', kwargs={'pk': self.object.pk})
# Bill of Materials Views

@login_required
@require_POST
def update_bom_from_cutting_ajax(request):
    cost_analysis_id = request.POST.get('cost_analysis_id')
    if not cost_analysis_id:
        return JsonResponse({'success': False, 'error': 'Cost Analysis ID is required.'}, status=400)

    try:
        analysis = get_object_or_404(ProductionCostAnalysis, pk=cost_analysis_id)
        order = analysis.production_order
        cutting_process = getattr(order, 'cutting_process', None)
        bom = getattr(order, 'bom_version', None)
        fabric_material = getattr(order.textile_stock, 'warehouse_product', None)
        
        if not all([cutting_process, bom, fabric_material]):
            return JsonResponse({'success': False, 'error': 'Missing cutting process, BOM, or fabric link.'}, status=400)

        new_meterage = cutting_process.single_layer_meterage
        if not new_meterage or new_meterage <= 0:
            return JsonResponse({'success': False, 'error': 'No valid cutting meterage available to update.'}, status=400)

        # Find and update the fabric item in the BOM
        bom_item, created = BOMItem.objects.get_or_create(
            bom=bom,
            material=fabric_material,
            defaults={'quantity': new_meterage}
        )

        if not created:
            bom_item.quantity = new_meterage
            bom_item.save()
            
        messages.success(request, f"تم تحديث متراج القماش في قائمة المواد إلى {new_meterage:.3f} بناءً على بيانات القص.")
        return JsonResponse({'success': True, 'message': 'BOM updated successfully.'})

    except ProductionCostAnalysis.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cost analysis not found.'}, status=404)
    except Exception as e:
        logging.error(f"Error in update_bom_from_cutting_ajax: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# Add these to your imports at the top
from django.db.models import Max

# ...

# (Replace the entire block of BillOfMaterials... views)
class BillOfMaterialsListView(LoginRequiredMixin, ListView):
    model = BillOfMaterials
    template_name = 'production/bom_list.html'
    context_object_name = 'bom_items'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = BillOfMaterials.objects.filter(is_active=True).select_related('product', 'created_by').order_by('product__name', 'size_group')
        
        product_filter = self.request.GET.get('product')
        if product_filter:
            queryset = queryset.filter(product_id=product_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(is_active=True, product_type='finished')
        return context

class BillOfMaterialsDetailView(LoginRequiredMixin, DetailView):
    model = BillOfMaterials
    template_name = 'production/bom_detail.html'
    context_object_name = 'bom'

    def get_object(self, queryset=None):
        """
        Overrides the default get_object to add performance optimizations
        by prefetching related data needed in the template.
        """
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)

        queryset = queryset.select_related(
            'product', 'size_group', 'created_by'
        ).prefetch_related(
            'items__material__unit_new'  # Assuming unit_new is the relation to the unit
        )
        
        obj = get_object_or_404(queryset, pk=pk)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bom = self.get_object() # Call our overridden method
        context['version_history'] = BillOfMaterials.objects.filter(
            product=bom.product, size_group=bom.size_group
        ).order_by('-version')
        return context
    
class BillOfMaterialsCreateView(LoginRequiredMixin, CreateView):
    model = BillOfMaterials
    form_class = BillOfMaterialsForm
    template_name = 'production/bom_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BOMItemFormSet(self.request.POST, prefix='items')
        else:
            copy_from_id = self.request.GET.get('copy_from')
            if copy_from_id:
                try:
                    source_bom = BillOfMaterials.objects.get(id=copy_from_id)
                    initial_data = [{'material': item.material, 'quantity': item.quantity, 'notes': item.notes} for item in source_bom.items.all()]
                    context['formset'] = BOMItemFormSet(prefix='items', initial=initial_data)
                    self.initial.update({'product': source_bom.product, 'size_group': source_bom.size_group, 'notes': f"Copy of v{source_bom.version}. {source_bom.notes}"})
                    context['form'] = self.get_form()
                except BillOfMaterials.DoesNotExist:
                    context['formset'] = BOMItemFormSet(prefix='items')
            else:
                context['formset'] = BOMItemFormSet(prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        with transaction.atomic():
            if formset.is_valid():
                form.instance.created_by = self.request.user
                
                BillOfMaterials.objects.filter(
                    product=form.instance.product, 
                    size_group=form.instance.size_group,
                    is_active=True
                ).update(is_active=False)

                form.instance.version = 1
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                messages.success(self.request, 'تم إنشاء قائمة المواد الجديدة بنجاح.')
                return redirect(reverse('production:bom_detail', kwargs={'pk': self.object.pk}))
            else:
                return self.form_invalid(form)

class BillOfMaterialsUpdateView(LoginRequiredMixin, UpdateView):
    model = BillOfMaterials
    form_class = BillOfMaterialsForm
    template_name = 'production/bom_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BOMItemFormSet(self.request.POST, prefix='items', instance=self.object)
        else:
            context['formset'] = BOMItemFormSet(prefix='items', instance=self.object)
        context['is_update_view'] = True
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if formset.is_valid():
            with transaction.atomic():
                old_bom = self.get_object()
                
                # FIX: Use the product and size group from the submitted form, not the old BOM.
                product = form.cleaned_data['product']
                size_group = form.cleaned_data['size_group']
                
                # Deactivate all other versions for the selected product/size_group combination
                BillOfMaterials.objects.filter(
                    product=product, 
                    size_group=size_group
                ).update(is_active=False)

                # Find the highest version number for the selected product and size group.
                latest_version = BillOfMaterials.objects.filter(
                    product=product,
                    size_group=size_group
                ).aggregate(max_version=Max('version'))['max_version'] or 0

                new_version_number = latest_version + 1

                # Create the new BOM with the correct, incremented version.
                new_bom = BillOfMaterials.objects.create(
                    product=product, # Use product from form
                    size_group=size_group, # Use size_group from form
                    notes=form.cleaned_data['notes'],
                    version=new_version_number,
                    parent=old_bom, # Keep track of where it came from
                    created_by=self.request.user,
                    is_active=True
                )
                
                new_items = []
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                        new_items.append(BOMItem(
                            bom=new_bom,
                            material=item_form.cleaned_data['material'],
                            quantity=item_form.cleaned_data['quantity'],
                            notes=item_form.cleaned_data.get('notes', '')
                        ))
                BOMItem.objects.bulk_create(new_items)

                messages.success(self.request, f'تم إنشاء إصدار جديد (v{new_bom.version}) بنجاح.')
                return redirect(reverse('production:bom_detail', kwargs={'pk': new_bom.pk}))
        else:
            return self.form_invalid(form)

class BillOfMaterialsDeleteView(LoginRequiredMixin, DeleteView):
    model = BillOfMaterials
    template_name = 'production/bom_confirm_delete.html'
    success_url = reverse_lazy('production:bom_list')

    def form_valid(self, request, *args, **kwargs):
        messages.success(self.request, 'تم حذف قائمة المواد بنجاح.')
        return super().form_valid(request, *args, **kwargs)

@login_required
def copy_bill_of_materials(request, pk):
    return redirect(f"{reverse('production:bom_create')}?copy_from={pk}")



@login_required
def search_raw_materials_ajax(request):
    """
    AJAX view to search for raw materials.
    FIXED: This version now uses a more efficient query and ensures warehouse data is correct.
    """
    term = request.GET.get('term', '')
    if len(term) < 2:
        return JsonResponse({'results': []})

    try:
        # Get all relevant warehouses once.
        raw_material_warehouses = Warehouse.objects.filter(
            warehouse_type__in=['components', 'textile'], is_active=True
        )
        
        # Filter products.
        materials = Product.objects.filter(
            (Q(name__icontains=term) | Q(code__icontains=term)) & Q(is_active=True)
        ).exclude(
            product_type='finished'
        ).select_related('unit_new')[:20]

        # Efficiently prefetch all stock items for the filtered materials in one go.
        material_ids = [m.id for m in materials]
        all_stock_items = StockItem.objects.filter(
            product_id__in=material_ids,
            warehouse__in=raw_material_warehouses
        ).select_related('warehouse')

        # Group stock items by material_id for easy lookup.
        stock_items_by_material = {}
        for si in all_stock_items:
            if si.product_id not in stock_items_by_material:
                stock_items_by_material[si.product_id] = []
            stock_items_by_material[si.product_id].append(si)

        results = []
        for material in materials:
            material_stock_items = stock_items_by_material.get(material.id, [])
            
            # Create a dictionary for quick lookup of stock by warehouse ID for this specific material.
            stock_by_warehouse_id = {si.warehouse_id: si.available_quantity for si in material_stock_items}

            # Calculate total available stock across all warehouses for this material.
            total_available = sum(stock_by_warehouse_id.values())

            # Build the warehouses_data list by iterating through ALL potential warehouses.
            warehouses_data = []
            for warehouse in raw_material_warehouses:
                warehouses_data.append({
                    'id': warehouse.id,
                    'name': warehouse.name,
                    'available_quantity': float(stock_by_warehouse_id.get(warehouse.id, Decimal('0.0')))
                })
                
            unit_symbol = material.unit_new.symbol if material.unit_new else 'وحدة'
            results.append({
                'id': material.id,
                'text': f"{material.name} ({material.code})",
                'name': material.name,
                'available': f"{total_available} {unit_symbol}", # For display in search results
                'unit': unit_symbol,
                'warehouses': warehouses_data, # The crucial list for the form logic
            })
            
        return JsonResponse({'results': results})
    except Exception as e:
        logging.error(f"Error in search_raw_materials_ajax: {e}")
        return JsonResponse({'results': []})
    
@login_required
def get_size_group_for_product_ajax(request):
    """
    REWRITTEN: This function now correctly queries the unified Product model
    and its related BillOfMaterials to find the size group.
    """
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'error': 'No product ID provided'}, status=400)
    
    try:
        product = Product.objects.get(id=product_id)
        # Find the active BOM for the product to get the size group
        active_bom = BillOfMaterials.objects.filter(product=product, is_active=True).first()
        
        if active_bom and active_bom.size_group:
            size_group = active_bom.size_group
            data = {
                'id': size_group.id,
                'name': size_group.name,
                'sizes': size_group.sizes
            }
            return JsonResponse({'size_group': data})
        else:
            # If no active BOM or no size group on BOM, check the product's own size groups
            if product.size_groups.exists():
                # Returning the first size group as a fallback
                size_group = product.size_groups.first()
                data = {
                    'id': size_group.id,
                    'name': size_group.name,
                    'sizes': size_group.sizes
                }
                return JsonResponse({'size_group': data})
            else:
                return JsonResponse({'size_group': None})
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    except Exception as e:
        logging.error(f"Error in get_size_group_for_product_ajax: {e}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)


@login_required
def get_stock_item_details_ajax(request):
    """
    REWRITTEN: This function replaces the old `get_fabric_stock_ajax`.
    It gets details for a selected StockItem to populate form fields dynamically.
    """
    stock_item_id = request.GET.get('stock_item_id')
    if not stock_item_id:
        return JsonResponse({'error': 'No Stock Item ID provided'}, status=400)

    try:
        # Use select_related to efficiently fetch the related Product in the same query
        stock_item = StockItem.objects.select_related('product').get(id=stock_item_id)
        product = stock_item.product

        # Ensure the selected item is actually a fabric
        if product.product_type != 'fabric':
            return JsonResponse({'error': 'Selected item is not a fabric.'}, status=400)

        data = {
            'available_quantity': float(stock_item.available_quantity),
            'cost_per_meter': float(product.cost_price), # Assuming cost_price is per meter for fabrics
            'color': product.colors,
            'width': float(product.width) if product.width else None,
        }
        return JsonResponse(data)
    except StockItem.DoesNotExist:
        return JsonResponse({'error': 'Stock Item not found'}, status=404)
    except Exception as e:
        # Log the error for debugging
        logging.error(f"Error in get_stock_item_details_ajax: {e}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)



@login_required
def get_manufacturer_details_ajax(request):
    """Get external manufacturer details"""
    manufacturer_id = request.GET.get('manufacturer_id')
    if manufacturer_id:
        try:
            manufacturer = ExternalManufacturer.objects.get(id=manufacturer_id)
            data = {
                'name': manufacturer.name,
                'contact_person': manufacturer.contact_person,
                'phone': manufacturer.phone,
                'price_per_piece': float(manufacturer.price_per_piece),
                'quality_rating': float(manufacturer.quality_rating),
                'payment_terms_days': manufacturer.payment_terms_days,
                'average_defect_rate': manufacturer.average_defect_rate,
            }
            return JsonResponse(data)
        except ExternalManufacturer.DoesNotExist:
            return JsonResponse({'error': 'Manufacturer not found'}, status=404)
    return JsonResponse({'error': 'No manufacturer ID provided'}, status=400)

@login_required
def update_process_status_ajax(request):
    """Update process status via AJAX"""
    if request.method == 'POST':
        process_type = request.POST.get('process_type')
        process_id = request.POST.get('process_id')
        action = request.POST.get('action')
        
        try:
            if process_type == 'cutting':
                process = CuttingProcess.objects.get(id=process_id)
                if action == 'complete':
                    process.is_completed = True
                    process.completed_at = timezone.now()
                    process.save()
                    process.production_order.status = 'in_assembly'
                    process.production_order.save()
                    
            elif process_type == 'assembly':
                process = AssemblyProcess.objects.get(id=process_id)
                if action == 'complete':
                    process.is_completed = True
                    process.actual_completion_date = timezone.now()
                    process.save()
                    process.production_order.status = 'in_dyeing'
                    process.production_order.save()
                    
            elif process_type == 'dyeing':
                process = DyeingProcess.objects.get(id=process_id)
                if action == 'complete':
                    process.is_completed = True
                    process.actual_return_date = timezone.now()
                    process.save()
                    process.assembly_process.production_order.status = 'in_finishing'
                    process.assembly_process.production_order.save()
                    
            elif process_type == 'finishing':
                process = FinishingProcess.objects.get(id=process_id)
                if action == 'complete':
                    process.is_completed = True
                    process.actual_completion_date = timezone.now()
                    process.save()
                    order = process.dyeing_process.assembly_process.production_order
                    order.status = 'completed'
                    order.actual_completion_date = timezone.now().date()
                    order.save()
            
            return JsonResponse({'success': True, 'message': 'تم تحديث الحالة بنجاح'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# Specialized Report Views
class DailyProductionReportView(LoginRequiredMixin, TemplateView):
    template_name = 'production/reports/daily_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        
        # إحصائيات اليوم
        context['daily_stats'] = {
            'orders_created': ProductionOrder.objects.filter(created_at__date=today).count(),
            'orders_completed': ProductionOrder.objects.filter(
                actual_completion_date=today
            ).count(),
            'cutting_completed': CuttingProcess.objects.filter(
                completed_at__date=today
            ).count(),
            'assembly_completed': AssemblyProcess.objects.filter(
                actual_completion_date__date=today
            ).count(),
            'dyeing_completed': DyeingProcess.objects.filter(
                actual_return_date__date=today
            ).count(),
            'finishing_completed': FinishingProcess.objects.filter(
                actual_completion_date__date=today
            ).count(),
        }
        
        # الأوامر النشطة
        context['active_orders'] = ProductionOrder.objects.filter(
            status__in=['approved', 'in_cutting', 'in_assembly', 'in_dyeing', 'in_finishing']
        ).select_related('product')[:10]
        
        return context

class WeeklyProductionReportView(LoginRequiredMixin, TemplateView):
    template_name = 'production/reports/weekly_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        
        # إحصائيات الأسبوع
        orders_this_week = ProductionOrder.objects.filter(
            created_at__date__gte=week_start
        )
        
        context['weekly_stats'] = {
            'orders_created': orders_this_week.count(),
            'orders_completed': orders_this_week.filter(status='completed').count(),
            'total_pieces': orders_this_week.aggregate(
                total=Sum('quantity_ordered')
            )['total'] or 0,
            'completion_rate': (
                orders_this_week.filter(status='completed').count() / 
                orders_this_week.count() * 100
                if orders_this_week.count() > 0 else 0
            ),
        }
        
        # تحليل الأداء حسب اليوم
        daily_performance = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            daily_orders = orders_this_week.filter(created_at__date=day)
            daily_performance.append({
                'date': day,
                'orders_created': daily_orders.count(),
                'orders_completed': daily_orders.filter(status='completed').count(),
            })
        
        context['daily_performance'] = daily_performance
        
        return context

class MonthlyProductionReportView(LoginRequiredMixin, TemplateView):
    template_name = 'production/reports/monthly_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        # إحصائيات الشهر
        orders_this_month = ProductionOrder.objects.filter(
            created_at__date__gte=month_start
        )
        
        context['monthly_stats'] = {
            'orders_created': orders_this_month.count(),
            'orders_completed': orders_this_month.filter(status='completed').count(),
            'total_pieces': orders_this_month.aggregate(
                total=Sum('quantity_ordered')
            )['total'] or 0,
            'total_fabric_used': orders_this_month.aggregate(
                total=Sum('fabric_meters_allocated')
            )['total'] or 0,
            'completion_rate': (
                orders_this_month.filter(status='completed').count() / 
                orders_this_month.count() * 100
                if orders_this_month.count() > 0 else 0
            ),
        }
        
        # تحليل الأداء حسب المنتج
        product_performance = orders_this_month.values(
            'product__name'
        ).annotate(
            total_orders=Count('id'),
            completed_orders=Count('id', filter=Q(status='completed')),
            total_pieces=Sum('quantity_ordered'),
            total_fabric=Sum('fabric_meters_allocated')
        ).order_by('-total_orders')
        
        context['product_performance'] = product_performance
        
        return context

# Textile-Specific Calculation Views
@login_required
def calculate_cutting_requirements(request, order_id):
    """Calculate cutting requirements for a production order"""
    order = get_object_or_404(ProductionOrder, pk=order_id)
    
    if request.method == 'POST':
        piece_length = float(request.POST.get('piece_length', 0))
        fabric_width = float(request.POST.get('fabric_width', order.textile_stock.width))
        pieces_per_width = int(request.POST.get('pieces_per_width', 1))
        
        if piece_length > 0:
            # حساب عدد القطع من طول القماش
            fabric_length = float(order.fabric_meters_allocated)
            pieces_per_length = int(fabric_length / piece_length)
            total_pieces_possible = pieces_per_length * pieces_per_width
            
            # إنشاء جدول القص
            cutting_data = {
                'fabric_length': fabric_length,
                'piece_length': piece_length,
                'fabric_width': fabric_width,
                'pieces_per_width': pieces_per_width,
                'pieces_per_length': pieces_per_length,
                'total_pieces_possible': total_pieces_possible,
                'required_pieces': order.quantity_ordered,
                'excess_pieces': max(0, total_pieces_possible - order.quantity_ordered),
                'fabric_utilization': min(100, (order.quantity_ordered / total_pieces_possible) * 100) if total_pieces_possible > 0 else 0,
            }
            
            return JsonResponse(cutting_data)
    
    context = {
        'order': order,
        'textile_stock': order.textile_stock,
    }
    return render(request, 'production/calculate_cutting.html', context)

@login_required
def create_cutting_table(request, order_id):
    """Create cutting table for production order"""
    order = get_object_or_404(ProductionOrder, pk=order_id)
    
    if request.method == 'POST':
        # إنشاء عملية القص
        cutting_process, created = CuttingProcess.objects.get_or_create(
            production_order=order,
            defaults={
                'cutter': request.user,
                'total_fabric_used': order.fabric_meters_allocated,
            }
        )
        
        # إنشاء جداول القص
        tables_data = json.loads(request.POST.get('tables_data', '[]'))
        
        for table_data in tables_data:
            CuttingTable.objects.create(
                cutting_process=cutting_process,
                fabric_length=table_data['fabric_length'],
                layers_count=table_data['layers_count'],
                pieces_per_layer=table_data['pieces_per_layer'],
                notes=table_data.get('notes', '')
            )
        
        # إنشاء القطع المقصوصة
        pieces_data = json.loads(request.POST.get('pieces_data', '[]'))
        
        for piece_data in pieces_data:
            CutPiece.objects.create(
                cutting_process=cutting_process,
                piece_type=piece_data['piece_type'],
                size=piece_data['size'],
                quantity=piece_data['quantity'],
                length=piece_data['length'],
                width=piece_data['width'],
                notes=piece_data.get('notes', '')
            )
        
        # تحديث إجمالي القطع المقصوصة
        cutting_process.total_pieces_cut = sum(
            piece['quantity'] for piece in pieces_data
        )
        cutting_process.save()
        
        messages.success(request, 'تم إنشاء جدول القص بنجاح.')
        return redirect('production:cutting_detail', pk=cutting_process.pk)
    
    context = {
        'order': order,
        'piece_types': CutPiece.PIECE_TYPES,
    }
    return render(request, 'production/create_cutting_table.html', context)

# Process Document Generation Views
@login_required
def generate_process_document(request, order_id, document_type):
    """Generate process documents for production orders"""
    order = get_object_or_404(ProductionOrder, pk=order_id)
    
    document_templates = {
        'cutting_order': 'production/documents/cutting_order.html',
        'assembly_order': 'production/documents/assembly_order.html',
        'dyeing_order': 'production/documents/dyeing_order.html',
        'finishing_order': 'production/documents/finishing_order.html',
        'quality_report': 'production/documents/quality_report.html',
        'cost_analysis': 'production/documents/cost_analysis.html',
    }
    
    if document_type not in document_templates:
        messages.error(request, 'نوع المستند غير صحيح.')
        return redirect('production:order_detail', pk=order_id)
    
    # إنشاء المستند
    document_number = f"{document_type.upper()}-{order.order_number}-{timezone.now().strftime('%Y%m%d%H%M')}"
    
    ProcessDocument.objects.create(
        production_order=order,
        document_type=document_type,
        document_number=document_number,
        title=f"{dict(ProcessDocument.DOCUMENT_TYPES)[document_type]} - {order.order_number}",
        content=f"تم إنشاء {dict(ProcessDocument.DOCUMENT_TYPES)[document_type]} لأمر الإنتاج {order.order_number}",
        created_by=request.user
    )
    
    context = {
        'order': order,
        'document_type': document_type,
        'document_number': document_number,
        'generated_at': timezone.now(),
        'generated_by': request.user,
    }
    
    # إضافة بيانات خاصة بكل نوع مستند
    if document_type == 'cutting_order':
        context['cutting_process'] = getattr(order, 'cutting_process', None)
        context['cutting_tables'] = order.cutting_process.cutting_tables.all() if hasattr(order, 'cutting_process') else []
        context['cut_pieces'] = order.cutting_process.cut_pieces.all() if hasattr(order, 'cutting_process') else []
    
    elif document_type == 'assembly_order':
        context['assembly_process'] = getattr(order, 'assembly_process', None)
        context['assembled_garments'] = order.assembly_process.assembled_garments.all() if hasattr(order, 'assembly_process') else []
    
    elif document_type == 'cost_analysis':
        context['cost_analysis'] = getattr(order, 'cost_analysis', None)
    
    template_name = document_templates[document_type]
    return render(request, template_name, context)

# Loss Analysis Views
class LossAnalysisView(LoginRequiredMixin, TemplateView):
    template_name = 'production/loss_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # تحليل الفاقد في القص
        cutting_losses = CuttingProcess.objects.filter(
            is_completed=True
        ).aggregate(
            total_fabric_used=Sum('total_fabric_used'),
            total_waste=Sum('fabric_waste')
        )
        
        cutting_waste_rate = 0
        if cutting_losses['total_fabric_used']:
            cutting_waste_rate = (cutting_losses['total_waste'] or 0) / cutting_losses['total_fabric_used'] * 100
        
        # تحليل الفاقد في التجميع
        assembly_losses = AssemblyProcess.objects.filter(
            is_completed=True
        ).aggregate(
            total_sent=Sum('quantity_sent'),
            total_losses=Sum('losses_count')
        )
        
        assembly_loss_rate = 0
        if assembly_losses['total_sent']:
            assembly_loss_rate = (assembly_losses['total_losses'] or 0) / assembly_losses['total_sent'] * 100
        
        # تحليل الفاقد في الصباغة
        dyeing_losses = DyeingProcess.objects.filter(
            is_completed=True
        ).aggregate(
            total_sent=Sum('quantity_sent'),
            total_losses=Sum('losses_count')
        )
        
        dyeing_loss_rate = 0
        if dyeing_losses['total_sent']:
            dyeing_loss_rate = (dyeing_losses['total_losses'] or 0) / dyeing_losses['total_sent'] * 100
        
        context['loss_analysis'] = {
            'cutting': {
                'total_fabric_used': cutting_losses['total_fabric_used'] or 0,
                'total_waste': cutting_losses['total_waste'] or 0,
                'waste_rate': cutting_waste_rate,
            },
            'assembly': {
                'total_sent': assembly_losses['total_sent'] or 0,
                'total_losses': assembly_losses['total_losses'] or 0,
                'loss_rate': assembly_loss_rate,
            },
            'dyeing': {
                'total_sent': dyeing_losses['total_sent'] or 0,
                'total_losses': dyeing_losses['total_losses'] or 0,
                'loss_rate': dyeing_loss_rate,
            },
        }
        
        return context

# External Manufacturer Performance Views
class ManufacturerPerformanceView(LoginRequiredMixin, TemplateView):
    template_name = 'production/manufacturer_performance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # تحليل أداء المصانع الخارجية
        manufacturers = ExternalManufacturer.objects.filter(is_active=True)
        performance_data = []
        
        for manufacturer in manufacturers:
            processes = manufacturer.assembly_processes.filter(is_completed=True)
            
            if processes.exists():
                total_sent = processes.aggregate(total=Sum('quantity_sent'))['total'] or 0
                total_received = processes.aggregate(total=Sum('quantity_received'))['total'] or 0
                total_defects = processes.aggregate(total=Sum('defects_count'))['total'] or 0
                total_losses = processes.aggregate(total=Sum('losses_count'))['total'] or 0
                
                performance_data.append({
                    'manufacturer': manufacturer,
                    'total_orders': processes.count(),
                    'total_sent': total_sent,
                    'total_received': total_received,
                    'total_defects': total_defects,
                    'total_losses': total_losses,
                    'efficiency_rate': (total_received / total_sent * 100) if total_sent > 0 else 0,
                    'defect_rate': (total_defects / total_received * 100) if total_received > 0 else 0,
                    'loss_rate': (total_losses / total_sent * 100) if total_sent > 0 else 0,
                    'average_cost': processes.aggregate(avg=Avg('cost_per_piece'))['avg'] or 0,
                })
        
        context['performance_data'] = performance_data
        return context

# Batch Tracking Views
class BatchTrackingView(LoginRequiredMixin, TemplateView):
    template_name = 'production/batch_tracking.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch_number = self.request.GET.get('batch_number')
        
        if batch_number:
            # البحث عن أوامر الإنتاج بهذا الباتش
            orders = ProductionOrder.objects.filter(
                batch_number__icontains=batch_number
            ).select_related('product', 'textile_stock')
            
            batch_history = []
            for order in orders:
                history = {
                    'order': order,
                    'cutting': getattr(order, 'cutting_process', None),
                    'assembly': order.assembly_processes.all(),
                    'dyeing': [],
                    'finishing': [],
                    'quality_checks': order.quality_checks.all(),
                }
                
                # جمع عمليات الصباغة والتشطيب
                for assembly in history['assembly']:
                    history['dyeing'].extend(assembly.dyeing_processes.all())
                    for dyeing in assembly.dyeing_processes.all():
                        history['finishing'].extend(dyeing.finishing_processes.all())
                
                batch_history.append(history)
            
            context['batch_history'] = batch_history
            context['batch_number'] = batch_number
        
        return context

# Production Workflow Management
@login_required
def workflow_status_view(request):
    """
    Provides a comprehensive overview of the entire production workflow,
    showing orders and processes at each stage.
    """
    
    # --- Orders waiting to start a process ---
    pending_orders = ProductionOrder.objects.filter(status='pending').select_related('product', 'created_by')
    cutting_queue = ProductionOrder.objects.filter(status='approved').select_related('product', 'created_by')
    assembly_queue = ProductionOrder.objects.filter(status='in_assembly', assembly_processes__isnull=True).select_related('product', 'created_by')
    dyeing_queue = AssemblyProcess.objects.filter(is_completed=True, dyeing_processes__isnull=True).select_related('production_order__product')
    finishing_queue = DyeingProcess.objects.filter(is_completed=True, finishing_process__isnull=True).select_related('assembly_process__production_order__product')

    # --- Active Processes (In Progress) ---
    active_cutting = CuttingProcess.objects.filter(is_completed=False).select_related('production_order__product', 'cutter')
    active_assembly = AssemblyProcess.objects.filter(is_completed=False).select_related('production_order__product', 'external_manufacturer', 'assembler')
    active_dyeing = DyeingProcess.objects.filter(is_completed=False).select_related('assembly_process__production_order__product', 'dyeing_facility')
    active_finishing = FinishingProcess.objects.filter(is_completed=False).select_related('dyeing_process__assembly_process__production_order__product', 'external_manufacturer', 'finisher')

    # --- Recently Completed ---
    recently_completed_orders = ProductionOrder.objects.filter(status='completed').order_by('-actual_completion_date').select_related('product')[:10]

    context = {
        'page_title': 'مراقبة سير العمل',
        'pending_orders': pending_orders,
        'cutting_queue': cutting_queue,
        'assembly_queue': assembly_queue,
        'dyeing_queue': dyeing_queue,
        'finishing_queue': finishing_queue,
        'active_cutting': active_cutting,
        'active_assembly': active_assembly,
        'active_dyeing': active_dyeing,
        'active_finishing': active_finishing,
        'recently_completed': recently_completed_orders,
    }
    
    return render(request, 'production/workflow_status.html', context)
# Fabric Utilization Calculator
@login_required
def fabric_utilization_calculator(request):
    """Calculate fabric utilization for different cutting patterns"""
    if request.method == 'POST':
        fabric_width = float(request.POST.get('fabric_width', 0))
        fabric_length = float(request.POST.get('fabric_length', 0))
        piece_width = float(request.POST.get('piece_width', 0))
        piece_length = float(request.POST.get('piece_length', 0))
        
        if all([fabric_width, fabric_length, piece_width, piece_length]):
            # حساب عدد القطع
            pieces_per_width = int(fabric_width / piece_width)
            pieces_per_length = int(fabric_length / piece_length)
            total_pieces = pieces_per_width * pieces_per_length
            
            # حساب المساحة المستخدمة
            used_width = pieces_per_width * piece_width
            used_length = pieces_per_length * piece_length
            used_area = used_width * used_length
            total_area = fabric_width * fabric_length
            
            # حساب نسبة الاستخدام
            utilization_rate = (used_area / total_area) * 100
            waste_area = total_area - used_area
            waste_percentage = (waste_area / total_area) * 100
            
            calculation_result = {
                'total_pieces': total_pieces,
                'pieces_per_width': pieces_per_width,
                'pieces_per_length': pieces_per_length,
                'used_area': used_area,
                'total_area': total_area,
                'waste_area': waste_area,
                'utilization_rate': utilization_rate,
                'waste_percentage': waste_percentage,
            }
            
            return JsonResponse(calculation_result)
    
    return render(request, 'production/fabric_calculator.html')

# Production Cost Calculator
@login_required
def production_cost_calculator(request):
    """Calculate production costs for different scenarios"""
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 0))
        fabric_cost_per_meter = float(request.POST.get('fabric_cost_per_meter', 0))
        fabric_meters_per_piece = float(request.POST.get('fabric_meters_per_piece', 0))
        thread_cost_per_piece = float(request.POST.get('thread_cost_per_piece', 0))
        assembly_cost_per_piece = float(request.POST.get('assembly_cost_per_piece', 0))
        dyeing_cost_per_piece = float(request.POST.get('dyeing_cost_per_piece', 0))
        finishing_cost_per_piece = float(request.POST.get('finishing_cost_per_piece', 0))
        overhead_percentage = float(request.POST.get('overhead_percentage', 0))
        
        # حساب التكاليف
        fabric_cost_total = quantity * fabric_meters_per_piece * fabric_cost_per_meter
        thread_cost_total = quantity * thread_cost_per_piece
        assembly_cost_total = quantity * assembly_cost_per_piece
        dyeing_cost_total = quantity * dyeing_cost_per_piece
        finishing_cost_total = quantity * finishing_cost_per_piece
        
        direct_cost = (fabric_cost_total + thread_cost_total + assembly_cost_total + 
                      dyeing_cost_total + finishing_cost_total)
        overhead_cost = direct_cost * (overhead_percentage / 100)
        total_cost = direct_cost + overhead_cost
        cost_per_piece = total_cost / quantity if quantity > 0 else 0
        
        cost_breakdown = {
            'quantity': quantity,
            'fabric_cost_total': fabric_cost_total,
            'thread_cost_total': thread_cost_total,
            'assembly_cost_total': assembly_cost_total,
            'dyeing_cost_total': dyeing_cost_total,
            'finishing_cost_total': finishing_cost_total,
            'direct_cost': direct_cost,
            'overhead_cost': overhead_cost,
            'total_cost': total_cost,
            'cost_per_piece': cost_per_piece,
        }
        
        return JsonResponse(cost_breakdown)
    
    return render(request, 'production/cost_calculator.html')




# Report Views
class CostAnalysisReportView(LoginRequiredMixin, TemplateView):
    template_name = 'production/reports/cost_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range from request
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
        if not end_date:
            end_date = timezone.now().date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get cost analysis data
        cost_analyses = ProductionCostAnalysis.objects.filter(
            analysis_date__date__range=[start_date, end_date]
        ).select_related('production_order', 'production_order__product')
        
        # Calculate totals
        total_production_cost = cost_analyses.aggregate(
            total=Sum('total_production_cost')
        )['total'] or 0
        
        total_material_cost = cost_analyses.aggregate(
            total=Sum('total_material_cost')
        )['total'] or 0
        
        total_process_cost = cost_analyses.aggregate(
            total=Sum('total_process_cost')
        )['total'] or 0
        
        context.update({
            'cost_analyses': cost_analyses,
            'start_date': start_date,
            'end_date': end_date,
            'total_production_cost': total_production_cost,
            'total_material_cost': total_material_cost,
            'total_process_cost': total_process_cost,
        })
        
        return context

class QualityReportView(LoginRequiredMixin, TemplateView):
    template_name = 'production/reports/quality_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range from request
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
        if not end_date:
            end_date = timezone.now().date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get quality checks
        quality_checks = QualityControlCheck.objects.filter(
            check_date__date__range=[start_date, end_date]
        ).select_related('production_order', 'inspector')
        
        # Calculate quality metrics
        total_checks = quality_checks.count()
        passed_checks = quality_checks.filter(approved=True).count()
        failed_checks = total_checks - passed_checks
        
        pass_rate = (passed_checks / total_checks * 100) if total_checks > 0 else 0
        
        # Average ratings by grade
        grade_distribution = quality_checks.values('overall_grade').annotate(
            count=Count('id')
        ).order_by('overall_grade')
        
        context.update({
            'quality_checks': quality_checks,
            'start_date': start_date,
            'end_date': end_date,
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'failed_checks': failed_checks,
            'pass_rate': round(pass_rate, 2),
            'grade_distribution': grade_distribution,
        })
        
        return context

# Export Views
@login_required
def export_production_orders(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="production_orders.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Order Number', 'Product', 'Quantity', 'Status', 'Priority',
        'Start Date', 'Expected Completion', 'Created At'
    ])
    
    orders = ProductionOrder.objects.select_related('product').all()
    
    for order in orders:
        writer.writerow([
            order.order_number,
            order.product.name,
            order.quantity_ordered,
            order.get_status_display(),
            order.get_priority_display(),
            order.start_date,
            order.expected_completion_date,
            order.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    return response


@login_required
def export_cost_analysis(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cost_analysis.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Production Order', 'Product', 'Total Production Cost', 'Material Cost',
        'Process Cost', 'Additional Cost', 'Cost Per Piece', 'Analysis Date'
    ])
    
    analyses = ProductionCostAnalysis.objects.select_related(
        'production_order', 'production_order__product'
    ).all()
    
    for analysis in analyses:
        writer.writerow([
            analysis.production_order.order_number,
            analysis.production_order.product.name,
            analysis.total_production_cost,
            analysis.total_material_cost,
            analysis.total_process_cost,
            analysis.total_additional_cost,
            analysis.cost_per_piece,
            analysis.analysis_date.strftime('%Y-%m-%d')
        ])
    
    return response

@login_required
def export_quality_reports(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="quality_reports.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Production Order', 'Check Type', 'Inspector', 'Items Checked',
        'Items Passed', 'Items Failed', 'Overall Grade', 'Check Date'
    ])
    
    checks = QualityControlCheck.objects.select_related(
        'production_order', 'inspector'
    ).all()
    
    for check in checks:
        writer.writerow([
            check.production_order.order_number,
            check.get_check_type_display(),
            check.inspector.username if check.inspector else '',
            check.items_checked,
            check.items_passed,
            check.items_failed,
            check.get_overall_grade_display(),
            check.check_date.strftime('%Y-%m-%d %H:%M')
        ])
    
    return response

# Print Views
@login_required
def print_production_order_pdf(request, pk):
    """
    Exports a single Production Order to a PDF file using wkhtmltopdf.
    """
    order = get_object_or_404(ProductionOrder.objects.select_related(
        'product', 'created_by', 'approved_by', 'bom_version'
    ).prefetch_related(
        'bom_version__items__material__unit_new'
    ), pk=pk)
    
    # Render HTML template to a string
    html = render_to_string('pdf/production/production_order_pdf.html', {'order': order})
    
    # Configure PDF options (copied from your bom_exports_blueprint)
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        '--header-font-name': 'Tajawal',
        '--footer-font-name': 'Tajawal',
        '--load-error-handling': 'ignore',
        '--load-media-error-handling': 'ignore',
    }

    try:
        # NOTE: Ensure WKHTMLTOPDF_PATH is configured in your settings.py
        pdf = pdfkit.from_string(html, False, options=options, configuration=pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH))
        
        # Create HTTP response
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Order_{order.order_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    except Exception as e:
        # Handle exceptions, e.g., wkhtmltopdf not found
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:order_detail', pk=pk)
class PrintExitPermitView(LoginRequiredMixin, DetailView):
    model = ExitPermit
    template_name = 'production/print/exit_permit.html'
    context_object_name = 'permit'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['print_date'] = timezone.now()
        return context

class PrintCuttingSheetView(LoginRequiredMixin, DetailView):
    model = CuttingProcess
    template_name = 'production/print/cutting_sheet.html'
    context_object_name = 'cutting_process'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['print_date'] = timezone.now()
        context['cutting_tables'] = self.object.cutting_tables.all()
        context['cut_pieces'] = self.object.cut_pieces.all()
        return context

class PrintQualityReportView(LoginRequiredMixin, DetailView):
    model = QualityControlCheck
    template_name = 'production/print/quality_report.html'
    context_object_name = 'quality_check'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['print_date'] = timezone.now()
        return context

# Add this import at the top if not already present
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import io

# Add this view function to your views.py file
@login_required
def bulk_print_orders(request):
    """Bulk print selected production orders"""
    order_ids = request.GET.getlist('order_ids')
    
    if not order_ids:
        messages.error(request, 'لم يتم تحديد أي أوامر للطباعة.')
        return redirect('production:order_list')
    
    # Get selected orders
    orders = ProductionOrder.objects.filter(
        id__in=order_ids
    ).select_related('product', 'textile_stock', 'created_by', 'approved_by')
    
    if not orders.exists():
        messages.error(request, 'لم يتم العثور على الأوامر المحددة.')
        return redirect('production:order_list')
    
    # Render template for printing
    template = get_template('production/print/bulk_orders.html')
    context = {
        'orders': orders,
        'print_date': timezone.now(),
        'total_orders': orders.count(),
        'total_quantity': orders.aggregate(total=Sum('quantity_ordered'))['total'] or 0,
    }
    
    html = template.render(context)
    
    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="bulk_orders_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
    
    # Generate PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        messages.error(request, 'حدث خطأ في إنشاء ملف PDF.')
        return redirect('production:order_list')
    
    return response

@login_required
def bulk_delete_orders(request):
    """Bulk delete selected production orders"""
    if request.method == 'POST':
        order_ids = request.POST.getlist('order_ids')
        
        if not order_ids:
            return JsonResponse({
                'success': False,
                'error': 'لم يتم تحديد أي أوامر للحذف'
            })
        
        try:
            # Get orders that can be deleted (only pending orders)
            orders_to_delete = ProductionOrder.objects.filter(
                id__in=order_ids,
                status='pending'  # Only allow deletion of pending orders
            )
            
            if not orders_to_delete.exists():
                return JsonResponse({
                    'success': False,
                    'error': 'لا يمكن حذف الأوامر المحددة. يمكن حذف الأوامر المعلقة فقط.'
                })
            
            deleted_count = orders_to_delete.count()
            orders_to_delete.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'تم حذف {deleted_count} أمر إنتاج بنجاح'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'حدث خطأ أثناء الحذف: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'طريقة الطلب غير صحيحة'
    })
@login_required
def update_order_status_ajax(request):
    """Update order status via AJAX"""
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        action = request.POST.get('action')
        
        try:
            order = ProductionOrder.objects.get(id=order_id)
            
            if action == 'approve':
                if order.status == 'pending':
                    order.status = 'approved'
                    order.approved_by = request.user
                    order.approved_at = timezone.now()
                    order.save()
                    return JsonResponse({
                        'success': True,
                        'message': f'تم اعتماد أمر الإنتاج {order.order_number}'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'لا يمكن اعتماد هذا الأمر في حالته الحالية'
                    })
            
            elif action == 'start':
                if order.status == 'approved':
                    order.status = 'in_cutting'
                    order.start_date = timezone.now().date()
                    order.save()
                    return JsonResponse({
                        'success': True,
                        'message': f'تم بدء إنتاج أمر {order.order_number}'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'لا يمكن بدء هذا الأمر في حالته الحالية'
                    })
            
            elif action == 'complete':
                if order.status in ['in_finishing', 'quality_check']:
                    order.status = 'completed'
                    order.actual_completion_date = timezone.now().date()
                    order.save()
                    return JsonResponse({
                        'success': True,
                        'message': f'تم إكمال أمر الإنتاج {order.order_number}'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'لا يمكن إكمال هذا الأمر في حالته الحالية'
                    })
            
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'إجراء غير صحيح'
                })
                
        except ProductionOrder.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'أمر الإنتاج غير موجود'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'حدث خطأ غير متوقع: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'طريقة الطلب غير صحيحة'
    })

@login_required
def print_orders_list(request):
    """Print orders list with current filters"""
    # Get filtered orders based on request parameters
    orders = ProductionOrder.objects.select_related('product', 'textile_stock').all()
    
    # Apply filters
    search = request.GET.get('search')
    if search:
        orders = orders.filter(
            Q(order_number__icontains=search) |
            Q(batch_number__icontains=search) |
            Q(product__name__icontains=search)
        )
    
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)
    
    priority = request.GET.get('priority')
    if priority:
        orders = orders.filter(priority=priority)
    
    context = {
        'orders': orders,
        'print_date': timezone.now(),
        'total_orders': orders.count(),
        'total_quantity': orders.aggregate(total=Sum('quantity_ordered'))['total'] or 0,
        'filters': {
            'search': search,
            'status': status,
            'priority': priority,
        }
    }
    
    return render(request, 'production/print/orders_list.html', context)

# Add this view after the existing textile stock views (around line 800)


@login_required
def batch_generator_view(request):
    """Generate batch numbers for production orders"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        manual_batch = request.POST.get('manual_batch')

        if manual_batch:
            batch_number = manual_batch
        elif product_id:
            product = get_object_or_404(Product, pk=product_id)
            today = timezone.now().date()
            counter = ProductionOrder.objects.filter(
                product=product,
                created_at__date=today
            ).count() + 1
            batch_number = f"BATCH-{product.code}-{today.strftime('%y%m%d')}-{counter:03d}"
        else:
            return JsonResponse({'error': 'Product ID is required for automatic generation.'}, status=400)

        return JsonResponse({'batch_number': batch_number})

    return JsonResponse({'error': 'Invalid request method'}, status=405)


# Add this AJAX view to your existing views.py file

@login_required
def get_warehouse_products_ajax(request):
    """Get products for a specific warehouse"""
    warehouse_id = request.GET.get('warehouse_id')
    if warehouse_id:
        try:
            from warehouses.models import Product
            products = Product.objects.filter(
                stock_items__warehouse_id=warehouse_id,
                is_active=True
            ).distinct().values('id', 'name', 'code')
            
            return JsonResponse({
                'success': True,
                'products': list(products)
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'error': 'No warehouse ID provided'
    })

# Add this view function to your existing views.py file


# Add these views to your existing views.py file



@login_required
def export_stock_movements(request, stock_item_id):
    """Export stock movements to CSV"""
    try:
        from warehouses.models import StockItem
        stock_item = get_object_or_404(StockItem, pk=stock_item_id)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="stock_movements_{stock_item.product.name}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow(['Stock Movements Report'])
        writer.writerow(['Product:', stock_item.product.name])
        writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([''])
        
        # Movements
        writer.writerow(['Date', 'Movement Type', 'Quantity', 'Reference', 'User', 'Notes'])
        
        for movement in stock_item.movements.all():
            writer.writerow([
                movement.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                movement.get_movement_type_display(),
                movement.quantity,
                movement.reference_number or '',
                movement.created_by.username if movement.created_by else '',
                movement.notes or ''
            ])
        
        return response
        
    except Exception as e:
        return HttpResponse(f'Error: {str(e)}', status=400)


# Add this view to your existing views.py file


@login_required
def export_finished_products(request):
    """
    REWRITTEN: This function now exports data from the unified Product model,
    filtered by product_type='finished'.
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="finished_products.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Name', 'Code', 'Category', 'Fabric Qty per Piece', 'Selling Price', 'Active'])
    
    # Query the unified Product model
    products = Product.objects.filter(product_type='finished').select_related('category')
    
    for product in products:
        writer.writerow([
            product.name,
            product.code,
            product.category.name if product.category else '',
            product.fabric_quantity_per_piece or 0,
            product.selling_price or 0,
            'نشط' if product.is_active else 'غير نشط'
        ])
    return response



# In production/views.py
# In production/views.py

@login_required
def get_order_details_ajax(request):
    order_id = request.GET.get('order_id')
    if not order_id:
        return JsonResponse({'success': False, 'error': 'No order ID provided'}, status=400)
    
    try:
        # We need the product and its related size groups.
        # prefetch_related is used for ManyToMany relationships like 'size_groups'.
        order = ProductionOrder.objects.select_related(
            'product', 
            'bom_version',
            'textile_stock__product'
        ).prefetch_related(
            'product__size_groups'  # Prefetch the M2M relationship from Product
        ).get(pk=order_id)
        
        product = order.product
        all_sizes = set() # Use a set to automatically handle duplicates

        # CORRECTED LOGIC: Collect all sizes from all of the product's associated size groups
        if product.size_groups.exists():
            for size_group in product.size_groups.all():
                # The 'sizes' field is a JSON list, so we add each item to our set
                for size in size_group.sizes:
                    all_sizes.add(size)
        
        # Create a dictionary with a sorted list of all unique sizes for the frontend
        size_data = {
            'sizes': sorted(list(all_sizes)) # Sort for a consistent order
        }

        # Safely access textile stock attributes
        fabric_name = order.textile_stock.product.name if order.textile_stock and order.textile_stock.product else "N/A"
        fabric_width = order.textile_stock.product.width if order.textile_stock and order.textile_stock.product else None

        data = {
            'success': True,
            'product_id': order.product.id,
            'product_name': order.product.name,
            'fabric_name': fabric_name,
            'fabric_width': float(fabric_width) if fabric_width else None,
            'quantity_ordered': order.quantity_ordered,
            'size_group': size_data, # Pass the new combined list of sizes
            'bom_version_id': order.bom_version.id if order.bom_version else None,
        }
        return JsonResponse(data)
    except ProductionOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    except Exception as e:
        import logging
        logging.error(f"Error in get_order_details_ajax: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An unexpected server error occurred.'}, status=500)

# In production/views.py

@login_required
def print_cutting_sheet_pdf(request, pk):
    """
    Exports a single Cutting Process sheet to a PDF file with all possible data.
    """
    process = get_object_or_404(CuttingProcess.objects.select_related(
        'production_order__product', 'cutter'
    ).prefetch_related(
        'cutting_tables', 'cut_pieces'
    ), pk=pk)

    context = {
        'cutting_process': process,
        'cutting_tables': process.cutting_tables.all(),
        'cut_pieces': process.cut_pieces.order_by('piece_type', 'size'),
        'cutting_stats': {
            'total_tables': process.cutting_tables.count(),
            'total_garments': process.total_pieces_cut,
            'total_individual_pieces': process.cut_pieces.aggregate(total=Sum('quantity'))['total'] or 0,
        },
        'timestamp': timezone.now()
    }
    
    html = render_to_string('pdf/production/cutting_sheet_pdf.html', context)
    
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        '--header-font-name': 'Tajawal',
        '--footer-font-name': 'Tajawal',
        '--load-error-handling': 'ignore',
        '--load-media-error-handling': 'ignore',
    }

    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html, False, configuration=pdf_config, options=options)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"CuttingSheet_{process.production_order.order_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:cutting_detail', pk=pk)
    
@login_required
def ajax_get_dyeing_process_details(request):
    """
    AJAX view to fetch details for a selected Dyeing Process.
    This is used in the Finishing form to show context about the selected item.
    """
    dyeing_process_id = request.GET.get('dyeing_process_id')
    if not dyeing_process_id:
        return JsonResponse({'error': 'Dyeing Process ID is required'}, status=400)

    try:
        # CORRECTED: The query now follows the correct path to the size_group
        process = DyeingProcess.objects.select_related(
            'assembly_process__production_order__product',
            'assembly_process__production_order__bom_version__size_group'
        ).get(pk=dyeing_process_id)

        order = process.assembly_process.production_order
        product = order.product
        bom = order.bom_version

        # CORRECTED: Get sizes from the BOM version's size group
        sizes = bom.size_group.sizes if bom and bom.size_group else []

        # Prepare the data to be sent back as JSON
        data = {
            'product_name': product.name,
            'order_number': order.order_number,
            'quantity': process.quantity_received,
            'status': order.get_status_display(),
            'sizes': sizes,
        }
        return JsonResponse({'success': True, 'data': data})
    except DyeingProcess.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Process not found'}, status=404)
    except Exception as e:
        logging.error(f"Error in ajax_get_dyeing_process_details: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)
@login_required
def ajax_get_bom_for_assembly(request):
    """
    AJAX view to fetch BOM components for a given assembly process, including
    detailed stock availability per warehouse.
    """
    assembly_id = request.GET.get('assembly_id')
    if not assembly_id:
        return JsonResponse({'error': 'Assembly ID is required'}, status=400)

    try:
        assembly = get_object_or_404(AssemblyProcess, pk=assembly_id)
        order = assembly.production_order
        bom = order.bom_version

        if not bom:
            return JsonResponse({'components': [], 'error': 'No active BOM for this order.'})

        components_data = []
        raw_material_warehouses = Warehouse.objects.filter(type='raw_materials', is_active=True)

        for item in bom.items.exclude(material__product_type='finished').select_related('material', 'material__unit_new'):
            stock_items = StockItem.objects.filter(product=item.material, warehouse__in=raw_material_warehouses).select_related('warehouse')
            
            available_stock_total = stock_items.aggregate(
                total=Coalesce(Sum(F('quantity') - F('reserved_quantity')), Decimal('0.0'))
            )['total']
            
            # This list now includes the available quantity for each warehouse
            available_warehouses = [{
                'id': si.warehouse.id,
                'name': si.warehouse.name,
                'available_quantity': si.available_quantity 
            } for si in stock_items if si.available_quantity > 0]

            components_data.append({
                'material_id': item.material.id,
                'name': item.material.name,
                'code': item.material.code,
                'unit': item.material.unit_new.symbol if item.material.unit_new else 'units',
                'available_stock': available_stock_total,
                'available_warehouses': available_warehouses,
            })
            
        return JsonResponse({'success': True, 'components': components_data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def send_additional_materials(request, pk):
    """
    Handles the submission of the 'Send Additional Materials' modal with robust validation.
    Checks all stock levels before initiating a database transaction.
    """
    assembly_process = get_object_or_404(AssemblyProcess, pk=pk, is_completed=False)
    redirect_url = reverse('production:manufacturers:manufacturer_detail', kwargs={'pk': assembly_process.external_manufacturer.pk})
    
    formset = SendAdditionalComponentFormSet(request.POST, prefix='materials')

    if not formset.is_valid():
        error_list = []
        for form_errors in formset.errors:
            for field, errors in form_errors.items():
                error_list.extend(errors)
        messages.error(request, "فشلت العملية. الأخطاء: " + " ".join(error_list))
        return redirect(redirect_url)

    items_to_process = [form.cleaned_data for form in formset if form.cleaned_data and form.cleaned_data.get('quantity_to_send', 0) > 0]

    if not items_to_process:
        messages.warning(request, "لم يتم تحديد كميات لأي مواد خام.")
        return redirect(redirect_url)

    # --- Pre-transaction stock validation ---
    stock_errors = []
    for item_data in items_to_process:
        material = item_data['material']
        quantity = item_data['quantity_to_send']
        source_warehouse = item_data['source_warehouse']
        try:
            stock_item = StockItem.objects.get(product=material, warehouse=source_warehouse)
            if stock_item.available_quantity < quantity:
                stock_errors.append(f"مخزون غير كافٍ لـ '{material.name}' (متاح: {stock_item.available_quantity}, مطلوب: {quantity})")
        except StockItem.DoesNotExist:
            stock_errors.append(f"المادة '{material.name}' غير موجودة في مخزن '{source_warehouse.name}'.")

    if stock_errors:
        messages.error(request, "فشل التحقق من المخزون: " + " ".join(stock_errors))
        return redirect(redirect_url)

    # --- All checks passed, proceed with transaction ---
    try:
        with transaction.atomic():
            permit_description_lines = [
                f"مواد خام إضافية للمصنع: {assembly_process.external_manufacturer.name}",
                f"خاص بأمر التشغيل: {assembly_process.production_order.order_number}"
            ]
            for item in items_to_process:
                unit_symbol = item['material'].unit_new.symbol if item['material'].unit_new else ''
                permit_description_lines.append(f"- {item['material'].name}: {item['quantity_to_send']} {unit_symbol}")

            exit_permit = ExitPermit.objects.create(
                production_order=assembly_process.production_order,
                assembly_process=assembly_process,
                permit_type='other',
                items_description='\n'.join(permit_description_lines),
                quantity=len(items_to_process),
                destination=assembly_process.external_manufacturer.name,
                purpose="إرسال مواد خام إضافية",
                requested_by=request.user,
                valid_until=timezone.now() + timedelta(days=7),
                status='approved',
                approved_by=request.user,
                approved_at=timezone.now(),
            )

            for item_data in items_to_process:
                component, created = AssemblyComponent.objects.get_or_create(
                    assembly_process=assembly_process,
                    material=item_data['material'],
                    source_warehouse=item_data['source_warehouse'],
                    defaults={'quantity_sent': item_data['quantity_to_send']}
                )
                if not created:
                    component.quantity_sent = F('quantity_sent') + item_data['quantity_to_send']
                    component.save(update_fields=['quantity_sent'])
                
                stock_item = StockItem.objects.get(product=item_data['material'], warehouse=item_data['source_warehouse'])
                StockMovement.objects.create(
                    stock_item=stock_item,
                    movement_type='out',
                    quantity=item_data['quantity_to_send'],
                    reference_number=f"PERMIT-{exit_permit.permit_number}",
                    notes=f"صرف مواد خام إضافية لعملية تجميع #{assembly_process.id}",
                    created_by=request.user
                )
            
            messages.success(request, f"تم إنشاء إذن الخروج {exit_permit.permit_number} وإرسال المواد بنجاح.")

    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع أثناء الحفظ: {e}")

    return redirect(redirect_url)


@login_required
def calculate_fabric_requirement_ajax(request):
    """
    Calculates all material requirements for a given product and quantity based on its active BOM.
    This is used by the Production Order creation form.
    """
    product_id = request.GET.get('product_id')
    quantity_str = request.GET.get('quantity')

    if not product_id or not quantity_str:
        return JsonResponse({'success': False, 'error': 'Product ID and quantity are required.'}, status=400)

    try:
        order_quantity = Decimal(quantity_str)
        if order_quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Quantity must be positive.'}, status=400)
            
        product = Product.objects.get(pk=product_id)

        # Find the active Bill of Materials for this product
        active_bom = BillOfMaterials.objects.filter(product=product, is_active=True).first()
        if not active_bom:
            return JsonResponse({'success': False, 'error': 'This product does not have an active Bill of Materials (BOM).'}, status=404)

        materials_data = []
        # FIX: Correctly pre-fetches the related material and its new unit object.
        bom_items = active_bom.items.select_related('material', 'material__unit_new').all()

        for item in bom_items:
            required_quantity = item.quantity * order_quantity
            
            # Check stock availability for this material across all warehouses
            stock_info = StockItem.objects.filter(product=item.material).aggregate(
                total_available=Coalesce(Sum(F('quantity') - F('reserved_quantity')), Decimal('0.0'))
            )
            available_quantity = stock_info.get('total_available') or Decimal('0.0')
            
            # Find the primary stock item for the fabric to link in the form
            textile_stock_id = None
            if item.material.product_type == 'fabric':
                # This logic assumes you want to link *a* stock item, preferably the one with the most stock.
                # You might need more specific logic if there are multiple fabric stock locations.
                fabric_stock = StockItem.objects.filter(product=item.material).order_by('-quantity').first()
                if fabric_stock:
                    textile_stock_id = fabric_stock.id

            materials_data.append({
                'name': item.material.name,
                'required_quantity': required_quantity,
                'available_quantity': available_quantity,
                # FIX: Uses the symbol from the new unit system, with a fallback to the old one.
                'unit': item.material.unit_new.symbol if item.material.unit_new else item.material.get_unit_display(),
                'is_available': available_quantity >= required_quantity,
                'material_type': item.material.product_type,
                'textile_stock_id': textile_stock_id,
            })

        return JsonResponse({
            'success': True,
            'bom_id': active_bom.id,
            'bom_version': active_bom.version,
            'materials': materials_data
        })

    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found.'}, status=404)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid quantity.'}, status=400)
    except Exception as e:
        # Log the error for debugging
        import logging
        logging.error(f"Error in calculate_fabric_requirement_ajax: {str(e)}")
        return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
def export_orders(request):
    """
    Exports production orders to a CSV file, applying the same filters as the list view.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="production_orders.csv"'
    # Add BOM to support Arabic characters in Excel
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    # Write the header row
    writer.writerow([
        'Order Number', 'Batch Number', 'Product Name', 'Product Code',
        'Quantity Ordered', 'Status', 'Priority', 'Start Date',
        'Expected Completion', 'Created At'
    ])

    # Get the same queryset as the list view to apply filters
    queryset = ProductionOrder.objects.select_related('product', 'created_by').all()

    # Apply filters from GET parameters
    if search_query := request.GET.get('search'):
        queryset = queryset.filter(
            Q(order_number__icontains=search_query) |
            Q(batch_number__icontains=search_query) |
            Q(product__name__icontains=search_query)
        )
    if status := request.GET.get('status'):
        queryset = queryset.filter(status=status)
    if priority := request.GET.get('priority'):
        queryset = queryset.filter(priority=priority)

    # Write data rows
    for order in queryset:
        writer.writerow([
            order.order_number,
            order.batch_number,
            order.product.name,
            order.product.code,
            order.quantity_ordered,
            order.get_status_display(),
            order.get_priority_display(),
            order.start_date,
            order.expected_completion_date,
            order.created_at.strftime('%Y-%m-%d %H:%M')
        ])

    return response

# Add this import at the top of your views.py if it's not there
# Add this import at the top of your views.py if it's not there
@login_required
def generate_sequential_codes_ajax(request):
    """
    AJAX view to generate the next sequential order and batch numbers based on the LAST existing number.
    """
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'success': False, 'error': 'Product ID is required.'}, status=400)

    try:
        product = Product.objects.get(pk=product_id)
        
        # --- CORRECTED: Order Number Logic ---
        today_str = timezone.now().strftime('%Y%m%d')
        last_order = ProductionOrder.objects.order_by('id').last()
        next_order_seq = 1
        if last_order and last_order.order_number and '-' in last_order.order_number:
            try:
                last_seq_part = last_order.order_number.split('-')[-1]
                next_order_seq = int(last_seq_part) + 1
            except (ValueError, IndexError):
                next_order_seq = (last_order.id or 0) + 1
        order_number = f"ORD-{today_str}-{next_order_seq}"

        # --- CORRECTED: Batch Number Logic ---
        today_short_str = timezone.now().strftime('%y%m%d')
        product_code_prefix = product.code[:3].upper() if product.code else 'PROD'
        
        last_batch_order = ProductionOrder.objects.filter(
            product__product_type=product.product_type,
            batch_number__startswith=f'BATCH-{product_code_prefix}-'
        ).order_by('id').last()

        next_batch_seq = 1
        if last_batch_order and last_batch_order.batch_number:
            try:
                parts = last_batch_order.batch_number.split('-')
                if len(parts) > 2:
                    last_seq = int(parts[2])
                    next_batch_seq = last_seq + 1
            except (ValueError, IndexError):
                next_batch_seq = ProductionOrder.objects.filter(product__product_type=product.product_type).count() + 1
        
        # Use the same next_id from the order number for the final part
        order_id_part = (last_order.id + 1) if last_order else 1
        batch_number = f"BATCH-{product_code_prefix}-{next_batch_seq:04d}-{today_short_str}-{order_id_part}"

        return JsonResponse({
            'success': True,
            'order_number': order_number,
            'batch_number': batch_number
        })

    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    
class OrderDataListView(LoginRequiredMixin, ListView):
    """
    View to display a list of all production orders for printing shipping labels.
    """
    model = ProductionOrder
    template_name = 'production/order_data_list.html'
    context_object_name = 'orders'
    paginate_by = 25

    def get_queryset(self):
        queryset = ProductionOrder.objects.select_related(
            'product', 'created_by'
        ).order_by('-start_date', '-created_at')
        
        # Add search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(order_number__icontains=search_query) |
                Q(batch_number__icontains=search_query) |
                Q(product__name__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "بيانات أوامر الإنتاج للطباعة"
        context['search_query'] = self.request.GET.get('search', '')
        return context


@login_required
def print_shipping_label_pdf(request, pk):
    """
    Generates an A5 PDF shipping label for a Production Order, including a QR code.
    """
    order = get_object_or_404(
        ProductionOrder.objects.select_related('product', 'bom_version__size_group'), 
        pk=pk
    )

    # --- FIX: The reverse call is now for the global URL name ---
    # It no longer needs the 'production:' namespace prefix.
    public_url = request.build_absolute_uri(
        reverse('public_order_detail', kwargs={'order_number': order.order_number})
    )

    # 2. Create QR code in memory
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(public_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 3. Convert image to base64 string to embed in HTML
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_code_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    # 4. Get sizes from the linked BOM
    sizes_list = []
    if order.bom_version and order.bom_version.size_group:
        sizes_list = order.bom_version.size_group.sizes
    
    context = {
        'order': order,
        'qr_code_base64': qr_code_base64,
        'sizes_str': ", ".join(sizes_list),
    }

    # 5. Render the HTML template
    html_string = render_to_string('pdf/production/shipping_label_a5.html', context)

    # 6. Configure PDF options for A5
    options = {
        'page-size': 'A5',
        'margin-top': '0.5in',
        'margin-right': '0.5in',
        'margin-bottom': '0.5in',
        'margin-left': '0.5in',
        'encoding': "UTF-8",
        'grayscale': '', 
        '--load-error-handling': 'ignore',
    }

    try:
        # Ensure WKHTMLTOPDF_PATH is configured in settings.py
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options=options)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"ShippingLabel_{order.order_number}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        logger.error(f"PDF generation error for order {pk}: {e}")
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:order_data_list')


def public_order_detail_view(request, order_number):
    """
    Public, no-login-required view to display order details.
    Accessed by scanning the QR code.
    """
    try:
        order = get_object_or_404(
            ProductionOrder.objects.select_related(
                'product', 
                'bom_version__size_group', 
                'cutting_process__cutter'
            ).prefetch_related(
                # --- FIX: Prefetch components and their related materials for efficiency ---
                'assembly_processes__components__material__unit_new',
                'assembly_processes__dyeing_processes__finishing_process__components__material__unit_new',
                'assembly_processes__external_manufacturer',
                'assembly_processes__assembler',
                'assembly_processes__dyeing_processes__dyeing_facility',
                'assembly_processes__dyeing_processes__finishing_process__external_manufacturer',
                'assembly_processes__dyeing_processes__finishing_process__finisher'
            ),
            order_number=order_number
        )

        status_workflow = [
            'draft', 'approved', 'in_cutting', 'in_assembly',
            'in_dyeing', 'in_finishing', 'completed'
        ]
        
        try:
            current_status_index = status_workflow.index(order.status)
        except ValueError:
            current_status_index = -1

        assembly_process = order.assembly_processes.first()
        dyeing_process = assembly_process.dyeing_processes.first() if assembly_process else None
        
        finishing_process = None
        if dyeing_process and hasattr(dyeing_process, 'finishing_process'):
            finishing_process = dyeing_process.finishing_process

        sizes_list = []
        if order.bom_version and order.bom_version.size_group:
            sizes_list = order.bom_version.size_group.sizes

        context = {
            'order': order,
            'sizes_str': ", ".join(sizes_list),
            'current_status_index': current_status_index,
            'cutting_process': getattr(order, 'cutting_process', None),
            'assembly_process': assembly_process,
            'dyeing_process': dyeing_process,
            'finishing_process': finishing_process,
        }
        return render(request, 'production/public_order_detail.html', context)
    except ProductionOrder.DoesNotExist:
        return HttpResponse("Order not found.", status=404)

