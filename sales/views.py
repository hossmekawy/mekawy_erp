import base64
from io import BytesIO

import openpyxl

import pdfkit
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, TemplateView
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.db import transaction
from decimal import Decimal
from django.template.loader import get_template
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
import qrcode
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SalesInvoice, InvoiceItem, PriceList, Payment
from .forms import SalesInvoiceForm, InvoiceItemFormSet, PriceListForm, UploadFileForm, PriceListItemForm , PriceListForm
from warehouses.models import Product, Warehouse, Category, StockItem
from crm.models import Customer
from Mekawy_ERP.settings import WKHTMLTOPDF_PATH
import pdfkit

# --- Standalone Page Views ---

class DashboardView(TemplateView):
    """
    Renders the main dashboard page.
    """
    template_name = 'sales/dashboard.html'

class POSView(TemplateView):
    """
    Renders the main Point of Sale (POS) interface.
    Passes necessary data like categories, customers, and warehouses to the template.
    NOW FILTERS WAREHOUSES AND CATEGORIES TO ONLY SHOW THOSE WITH FINISHED PRODUCTS.
    """
    template_name = 'sales/pos.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Filter warehouses to only include those that have stock of finished products.
        context['warehouses'] = Warehouse.objects.filter(
            is_active=True,
            stock_items__product__product_type='finished',
            stock_items__quantity__gt=0
        ).distinct().order_by('name')

        # Filter categories to only include those associated with a finished product.
        context['categories'] = Category.objects.filter(
            product__product_type='finished',
            product__is_active=True
        ).distinct().order_by('name')
        
        context['customers'] = Customer.objects.filter(is_active=True)
        return context

# --- API Views for POS Frontend ---

class ProductListAPIView(APIView):
    def get(self, request, *args, **kwargs):
        warehouse_id = request.GET.get('warehouse_id')
        
        products_qs = Product.objects.select_related('category').filter(
            is_active=True, 
            product_type='finished'
        ).order_by('name')

        if warehouse_id and warehouse_id != 'all':
            products_qs = products_qs.filter(
                stock_items__warehouse_id=warehouse_id, 
                stock_items__quantity__gt=0
            ).distinct()

        data = []
        for p in products_qs:
            stock_qty = p.get_stock_for_warehouse(warehouse_id) if (warehouse_id and warehouse_id != 'all') else p.get_total_stock()
            
            if stock_qty > 0:
                price = p.selling_price or Decimal('0.00')
                
                data.append({
                    'id': p.id,
                    'name': p.name,
                    'code': p.code,
                    'category': p.category.name if p.category else 'Uncategorized',
                    'price': price,
                    'quantity': stock_qty,
                })
        return Response(data)

class CustomerSearchAPIView(View):
    """
    API endpoint for searching customers dynamically.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        if not query:
            return JsonResponse([], safe=False)
        
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(company_name__icontains=query) |
            Q(phone_number__icontains=query)
        )[:10]
        
        results = [{'id': c.id, 'text': str(c)} for c in customers]
        return JsonResponse(results, safe=False)


class CreateInvoiceAPIView(APIView):
    """
    API endpoint to create a sales invoice.
    Processes discount and returns detailed invoice data for printing and WhatsApp.
    NOW DEDUCTS SOLD QUANTITY FROM INVENTORY.
    """
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        data = request.data
        
        try:
            customer = get_object_or_404(Customer, id=data.get('customer_id'))
            warehouse = get_object_or_404(Warehouse, id=data.get('warehouse_id'))

            invoice = SalesInvoice.objects.create(
                customer=customer,
                warehouse=warehouse,
                created_by=request.user,
                status='PAID',
                discount_amount=Decimal(str(data.get('discount_amount', 0))),
            )

            for item_data in data.get('items', []):
                product = get_object_or_404(Product, id=item_data['id'])
                quantity_sold = Decimal(str(item_data['quantity']))
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity_sold,
                    unit_price=Decimal(str(item_data['price'])),
                )

                # Deduct from inventory
                stock_item = get_object_or_404(StockItem, product=product, warehouse=warehouse)
                if stock_item.quantity < quantity_sold:
                    raise Exception(f"Not enough stock for {product.name}. Available: {stock_item.quantity}, Tried to sell: {quantity_sold}")
                stock_item.quantity -= quantity_sold
                stock_item.save()
            
            for payment_data in data.get('payments', []):
                Payment.objects.create(
                    invoice=invoice,
                    method=payment_data['method'],
                    amount=Decimal(str(payment_data['amount'])),
                    transaction_id=payment_data.get('transaction_id'),
                )

            invoice.calculate_totals()

            invoice_data = {
                'invoice_number': invoice.invoice_number,
                'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                'customer': {
                    'name': customer.name,
                    'phone_number': str(customer.phone_number) if customer.phone_number else ''
                },
                'items': [{
                    'name': item.product.name,
                    'quantity': float(item.quantity),
                    'unit_price': float(item.unit_price),
                    'total': float(item.total)
                } for item in invoice.items.all()],
                'subtotal': float(invoice.subtotal),
                'discount_amount': float(invoice.discount_amount),
                'total': float(invoice.total)
            }
            
            return Response(invoice_data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({'error': f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

# --- Standard CRUD Views for Back-Office Management ---

class SalesInvoiceListView(LoginRequiredMixin, ListView):
    model = SalesInvoice
    template_name = 'sales/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

class SalesInvoiceDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = SalesInvoice
    template_name = 'sales/invoice_detail.html'
    context_object_name = 'invoice'

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.get_object()

        # --- QR Code Generation ---
        qr_data = f"""
        اسم البائع: اسم شركتك
        الرقم الضريبي للبائع: 123456789012345
        تاريخ الفاتورة: {invoice.issue_date.strftime('%Y-%m-%dT%H:%M:%SZ')}
        إجمالي الفاتورة: {invoice.total}
        إجمالي الضريبة: {invoice.tax_amount}
        """
        
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        context['qr_code_image'] = img_str
        return context

# --- PDF Generation View ---
class GenerateInvoicePDF(LoginRequiredMixin, UserPassesTestMixin, View):
    
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        invoice = get_object_or_404(SalesInvoice, pk=self.kwargs.get('pk'))

        # --- Generate QR Code (same as in DetailView) ---
        qr_data = f"UUID: {invoice.uuid}, Total: {invoice.total}, Tax: {invoice.tax_amount}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        context = {
            'invoice': invoice,
            'qr_code_image': img_str,
        }
        
        html_string = render_to_string('sales/invoice_pdf_template.html', context)
        pdf = pdfkit.from_string(html_string, False)

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
        
        return response


class SalesInvoiceCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form.html'
    success_url = reverse_lazy('sales:invoice_list')

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = InvoiceItemFormSet(self.request.POST)
        else:
            data['items'] = InvoiceItemFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        with transaction.atomic():
            form.instance.created_by = self.request.user
            self.object = form.save()
            if items.is_valid():
                items.instance = self.object
                items.save()
                self.object.calculate_totals()
                messages.success(self.request, "تم إنشاء الفاتورة بنجاح.")
            else:
                messages.error(self.request, "يرجى تصحيح الأخطاء في بنود الفاتورة.")
                return self.form_invalid(form)
        return super().form_valid(form)

class SalesInvoiceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form.html'

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = InvoiceItemFormSet(self.request.POST, instance=self.object)
        else:
            data['items'] = InvoiceItemFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        with transaction.atomic():
            self.object = form.save()
            if items.is_valid():
                items.instance = self.object
                items.save()
                self.object.calculate_totals()
                messages.success(self.request, "تم تحديث الفاتورة بنجاح.")
            else:
                messages.error(self.request, "يرجى تصحيح الأخطاء في بنود الفاتورة.")
                return self.form_invalid(form)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('sales:invoice_detail', kwargs={'pk': self.object.pk})

class PriceListView(LoginRequiredMixin, ListView):
    model = PriceList
    template_name = 'sales/pricelist_list.html'
    context_object_name = 'pricelists'
    paginate_by = 20

class PriceListCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = PriceList
    form_class = PriceListForm
    template_name = 'sales/pricelist_form.html'
    success_url = reverse_lazy('sales:pricelist_list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء قائمة الأسعار بنجاح.")
        return super().form_valid(form)

class ProductPriceListView(LoginRequiredMixin, View):
    """
    Displays a list of finished products for price editing.
    Handles search and pagination.
    """
    template_name = 'sales/product_price_list.html'
    
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        product_list = Product.objects.filter(product_type='finished').order_by('name')
        if query:
            product_list = product_list.filter(
                Q(name__icontains=query) | Q(code__icontains=query)
            )

        paginator = Paginator(product_list, 25) # Show 25 products per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        upload_form = UploadFileForm()

        context = {
            'products': page_obj,
            'upload_form': upload_form,
            'search_query': query
        }
        return render(request, self.template_name, context)

class UpdateProductPriceAJAXView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to update a product's selling price.
    """
    def post(self, request, *args, **kwargs):
        product_id = request.POST.get('product_id')
        new_price_str = request.POST.get('new_price')

        if not product_id or new_price_str is None:
            return JsonResponse({'status': 'error', 'message': 'بيانات غير كاملة.'}, status=400)

        try:
            product = Product.objects.get(id=product_id, product_type='finished')
            new_price = Decimal(new_price_str)
            
            if new_price < 0:
                 return JsonResponse({'status': 'error', 'message': 'السعر لا يمكن أن يكون سالباً.'}, status=400)

            product.selling_price = new_price
            product.save()
            return JsonResponse({'status': 'success', 'message': 'تم تحديث السعر بنجاح.'})

        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'المنتج غير موجود.'}, status=404)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'قيمة السعر غير صالحة.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'حدث خطأ: {e}'}, status=500)

class ExportPricesExcelView(LoginRequiredMixin, View):
    """
    Exports product prices to an Excel file.
    """
    def get(self, request, *args, **kwargs):
        products = Product.objects.filter(product_type='finished').order_by('name')
        
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = 'أسعار المنتجات'
        
        # Set headers
        headers = ['كود المنتج', 'اسم المنتج', 'سعر البيع']
        sheet.append(headers)
        
        # Add data
        for product in products:
            sheet.append([product.code, product.name, product.selling_price])
            
        # Create response
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="product_prices.xlsx"'
        virtual_workbook = BytesIO()
        workbook.save(virtual_workbook)
        response.write(virtual_workbook.getvalue())
        
        return response

class ImportPricesExcelView(LoginRequiredMixin, View):
    """
    Imports product prices from an Excel file.
    """
    def post(self, request, *args, **kwargs):
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['file']
            try:
                workbook = openpyxl.load_workbook(excel_file)
                sheet = workbook.active
                
                updated_count = 0
                errors = []

                # Skip header row
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    product_code, _, new_price = row[0], row[1], row[2]
                    
                    if not product_code or new_price is None:
                        continue
                        
                    try:
                        product = Product.objects.get(code=product_code, product_type='finished')
                        product.selling_price = Decimal(new_price)
                        product.save()
                        updated_count += 1
                    except Product.DoesNotExist:
                        errors.append(f"المنتج بالكود '{product_code}' غير موجود.")
                    except (ValueError, TypeError):
                        errors.append(f"قيمة السعر غير صالحة للمنتج بالكود '{product_code}'.")

                if errors:
                    messages.warning(request, f"تم تحديث {updated_count} منتج مع وجود الأخطاء التالية: {', '.join(errors)}")
                else:
                    messages.success(request, f"تم تحديث أسعار {updated_count} منتج بنجاح.")

            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء معالجة الملف: {e}")
        else:
            messages.error(request, "لم يتم رفع ملف أو أن الملف غير صالح.")
            
        return redirect('sales:product_price_list')

class ExportPricesPDFView(LoginRequiredMixin, View):
    """
    Exports product prices to a PDF file using wkhtmltopdf.
    """
    def get(self, request, *args, **kwargs):
        products = Product.objects.filter(product_type='finished').order_by('name')
        
        context = {
            'products': products,
            'company_name': 'Mekawy Group'
        }
        
        template = get_template('pdf/sales/price_list_pdf.html')
        html = template.render(context)
        
        try:
            config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
            pdf = pdfkit.from_string(html, False, configuration=config, options={
                'encoding': "UTF-8",
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
            })
            
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="product_prices.pdf"'
            
            return response
            
        except FileNotFoundError:
            messages.error(request, "خطأ: لم يتم العثور على wkhtmltopdf. يرجى التأكد من تثبيته وتعيين المسار الصحيح في الإعدادات.")
            return redirect('sales:product_price_list')
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء ملف PDF: {e}")
            return redirect('sales:product_price_list')

class SalesInvoiceDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = SalesInvoice
    success_url = reverse_lazy('sales:invoice_list')
    template_name = 'sales/invoice_confirm_delete.html'

    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        with transaction.atomic():
            # Add back the stock for each item in the invoice
            for item in self.object.items.all():
                StockItem.objects.filter(
                    product=item.product,
                    warehouse=self.object.warehouse
                ).update(quantity=Sum('quantity') + item.quantity)
            
            invoice_number = self.object.invoice_number
            self.object.delete()
            messages.success(request, f"Invoice {invoice_number} has been deleted and stock has been restored.")
        return redirect(self.get_success_url())
