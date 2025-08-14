from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Customer, Interaction
from .forms import CustomerForm, InteractionForm
from django.db import models # Added for Q objects
from django.contrib.auth.decorators import login_required

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'crm/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                models.Q(name__icontains=search_query) |
                models.Q(company_name__icontains=search_query) |
                models.Q(phone_number__icontains=search_query)
            )
        return queryset

class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'crm/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['interaction_form'] = InteractionForm()
        context['interactions'] = self.object.interactions.all()
        return context

class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'crm/customer_form.html'
    success_url = reverse_lazy('crm:customer_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "تم إضافة العميل بنجاح.")
        return super().form_valid(form)

    def form_invalid(self, form):
        # This method catches form errors and sends them to the messages framework
        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field != '__all__' else 'خطأ عام'
                messages.error(self.request, f"خطأ في حقل '{field_label}': {error}")
        return super().form_invalid(form)


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'crm/customer_form.html'
    
    def get_success_url(self):
        return reverse_lazy('crm:customer_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث بيانات العميل بنجاح.")
        return super().form_valid(form)

    def form_invalid(self, form):
        # This method catches form errors and sends them to the messages framework
        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field != '__all__' else 'خطأ عام'
                messages.error(self.request, f"خطأ في حقل '{field_label}': {error}")
        return super().form_invalid(form)


@login_required
def add_interaction(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = InteractionForm(request.POST)
        if form.is_valid():
            interaction = form.save(commit=False)
            interaction.customer = customer
            interaction.user = request.user
            interaction.save()
            messages.success(request, "تم تسجيل التفاعل بنجاح.")
        else:
            messages.error(request, "حدث خطأ أثناء تسجيل التفاعل.")
    return redirect('crm:customer_detail', pk=pk)
