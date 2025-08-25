from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from .models import SalesInvoice, PriceList
from .forms import SalesInvoiceForm, InvoiceItemFormSet, PriceListForm
from warehouses.models import Product, Warehouse
from crm.models import Customer

class SalesInvoiceListView(ListView):
    model = SalesInvoice
    template_name = 'sales/invoice_list.html'
    context_object_name = 'invoices'

class SalesInvoiceDetailView(DetailView):
    model = SalesInvoice
    template_name = 'sales/invoice_detail.html'
    context_object_name = 'invoice'

class SalesInvoiceCreateView(CreateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form_pos.html' # Use the new professional POS template
    success_url = reverse_lazy('sales:invoice_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = InvoiceItemFormSet(self.request.POST)
        else:
            data['items'] = InvoiceItemFormSet()
        # Pass warehouses to the template for the selection buttons
        data['warehouses'] = Warehouse.objects.filter(is_active=True)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        if items.is_valid():
            self.object = form.save(commit=False)
            self.object.created_by = self.request.user
            self.object.save()
            items.instance = self.object
            items.save()
            messages.success(self.request, "تم إنشاء الفاتورة بنجاح.")
            return redirect(self.get_success_url())
        else:
            # Provide detailed feedback on form errors
            error_message = "يرجى تصحيح الأخطاء التالية: "
            for field, errors in form.errors.items():
                error_message += f"{form.fields[field].label}: {', '.join(errors)} "
            for error in items.non_form_errors():
                 error_message += f"خطأ في البنود: {error} "
            messages.error(self.request, error_message)
            return self.render_to_response(self.get_context_data(form=form, items=items))


class SalesInvoiceUpdateView(UpdateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoice_form_pos.html' # Use the new professional POS template

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = InvoiceItemFormSet(self.request.POST, instance=self.object)
        else:
            data['items'] = InvoiceItemFormSet(instance=self.object)
        data['warehouses'] = Warehouse.objects.filter(is_active=True)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        if items.is_valid():
            self.object = form.save()
            items.instance = self.object
            items.save()
            messages.success(self.request, "تم تحديث الفاتورة بنجاح.")
            return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))

class PriceListView(ListView):
    model = PriceList
    template_name = 'sales/pricelist_list.html'
    context_object_name = 'pricelists'

class PriceListCreateView(CreateView):
    model = PriceList
    form_class = PriceListForm
    template_name = 'sales/pricelist_form.html'
    success_url = reverse_lazy('sales:pricelist_list')

class CustomerSearchAPIView(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        if not query:
            return JsonResponse([], safe=False)
        
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(company_name__icontains=query) |
            Q(phone_number__icontains=query)
        )[:10]
        
        data = [{
            'id': c.id,
            'name': c.name,
            'company': c.company_name,
            'phone': str(c.phone_number)
        } for c in customers]
        
        return JsonResponse(data, safe=False)
