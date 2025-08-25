from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.db import transaction
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SalesInvoice, InvoiceItem, PriceList, Payment
from .forms import SalesInvoiceForm, InvoiceItemFormSet, PriceListForm
from warehouses.models import Product, Warehouse, Category
from crm.models import Customer

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
    """
    template_name = 'sales/pos.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['customers'] = Customer.objects.filter(is_active=True)
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
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
                # FIX: Prevent TypeError by ensuring selling_price is never None.
                # It will default to Decimal('0.00') if the price is null in the database.
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
    NOW RETURNS DETAILED INVOICE DATA FOR PRINTING AND WHATSAPP.
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
                # NEW: Save the discount amount from the POS
                discount_amount=Decimal(data.get('discount_amount', 0)),
            )

            for item_data in data.get('items', []):
                product = get_object_or_404(Product, id=item_data['id'])
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=Decimal(item_data['quantity']),
                    unit_price=Decimal(item_data['price']),
                )
            
            for payment_data in data.get('payments', []):
                Payment.objects.create(
                    invoice=invoice,
                    method=payment_data['method'],
                    amount=Decimal(payment_data['amount']),
                    transaction_id=payment_data.get('transaction_id'),
                )

            invoice.calculate_totals()

            # NEW: Serialize and return the full invoice data for the frontend
            invoice_data = {
                'invoice_number': invoice.invoice_number,
                'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                'customer': {
                    'name': customer.name,
                    'phone_number': str(customer.phone_number)
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# --- Standard CRUD Views for Back-Office Management ---

class SalesInvoiceListView(ListView):
    model = SalesInvoice
    template_name = 'sales/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

class SalesInvoiceDetailView(DetailView):
    model = SalesInvoice
    template_name = 'sales/invoice_detail.html'
    context_object_name = 'invoice'

class SalesInvoiceCreateView(CreateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form.html'
    success_url = reverse_lazy('sales:invoice_list')

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

class SalesInvoiceUpdateView(UpdateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form.html'

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

class PriceListView(ListView):
    model = PriceList
    template_name = 'sales/pricelist_list.html'
    context_object_name = 'pricelists'
    paginate_by = 20

class PriceListCreateView(CreateView):
    model = PriceList
    form_class = PriceListForm
    template_name = 'sales/pricelist_form.html'
    success_url = reverse_lazy('sales:pricelist_list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء قائمة الأسعار بنجاح.")
        return super().form_valid(form)
