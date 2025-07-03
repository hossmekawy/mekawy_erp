from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.db.models import Q, F, Sum, Count, ExpressionWrapper
from django.db import transaction  # Import transaction module
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import pdfkit
from django.db.models import ProtectedError
from .models import Category, Warehouse, Product, StockItem, StockMovement, StockTransfer
# Add the missing import at the top of the file
from django.http import HttpResponse
from decimal import Decimal, InvalidOperation

import json
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
import csv
from datetime import datetime, timedelta
from .forms import CategoryForm, StockItemUpdateForm, WarehouseForm, ProductForm, StockItemForm, UnitForm,UnitConversionForm
# views.py

class WarehouseDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'warehouses/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_warehouses': Warehouse.objects.filter(is_active=True).count(),
            'total_products': Product.objects.filter(is_active=True).count(),
            'low_stock_items': StockItem.objects.filter(quantity__lte=F('product__min_stock_level')).count(),
            'pending_transfers': StockTransfer.objects.filter(status='pending').count(),
            'recent_movements': StockMovement.objects.select_related('stock_item__product', 'created_by')[:10],
        })
        return context

# Categories
class CategoryListView(LoginRequiredMixin, PermissionRequiredMixin,ListView):
    model = Category
    template_name = 'warehouses/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20
    permission_required = 'warehouses.view_category'
    def get_queryset(self):
        queryset = Category.objects.all()
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
            
        return queryset.order_by('name')

class CategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'warehouses/category_form.html'
    success_url = reverse_lazy('warehouses:category_list')
    permission_required = 'warehouses.add_category'
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة التصنيف بنجاح!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء المذكورة.')
        return super().form_invalid(form)

class CategoryDetailView(LoginRequiredMixin, PermissionRequiredMixin,DetailView):
    model = Category
    template_name = 'warehouses/category_detail.html'
    context_object_name = 'category'
    permission_required = 'warehouses.view_category'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = self.object.product_set.all()[:10]  # Show first 10 products
        context['products_count'] = self.object.product_set.count()
        return context

class CategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'warehouses/category_form.html'
    success_url = reverse_lazy('warehouses:category_list')
    permission_required = 'warehouses.change_category'
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث التصنيف بنجاح!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء المذكورة.')
        return super().form_invalid(form)

class CategoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Category
    template_name = 'warehouses/category_confirm_delete.html'
    success_url = reverse_lazy('warehouses:category_list')
    required_roles = ['admin']
    permission_required = 'warehouses.delete_category'
class CategorySearchView(LoginRequiredMixin, PermissionRequiredMixin,View):
    def get(self, request):
        search = request.GET.get('q', '')
        categories = Category.objects.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )[:10]
        
        data = [{'id': cat.id, 'name': cat.name} for cat in categories]
        return JsonResponse({'categories': data})

# Products
class ProductListView(LoginRequiredMixin, PermissionRequiredMixin,ListView):
    model = Product
    template_name = 'warehouses/product_list.html'
    context_object_name = 'products'
    paginate_by = 25
    permission_required = 'warehouses.view_product'
    def get_queryset(self):
        queryset = Product.objects.select_related('category').all()
        search = self.request.GET.get('search')
        category = self.request.GET.get('category')
        product_type = self.request.GET.get('product_type')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search) | 
                Q(barcode__icontains=search)
            )
        if category:
            queryset = queryset.filter(category_id=category)
        if product_type:
            queryset = queryset.filter(product_type=product_type)
            
        return queryset.order_by('name')

class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm # Use the new comprehensive form
    template_name = 'warehouses/product_form.html'
    success_url = reverse_lazy('warehouses:product_list')
    permission_required = 'warehouses.add_product'

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المنتج بنجاح.")
        return super().form_valid(form)

class ProductDetailView(LoginRequiredMixin,PermissionRequiredMixin, DetailView):
    model = Product
    template_name = 'warehouses/product_detail.html'
    context_object_name = 'product'
    permission_required = 'warehouses.view_product'


    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context['stock_items'] = StockItem.objects.filter(product=product).select_related('warehouse')
        context['recent_movements'] = StockMovement.objects.filter(
            stock_item__product=product
        ).select_related('stock_item__warehouse', 'created_by')[:10]
        return context

class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm # Use the new comprehensive form
    template_name = 'warehouses/product_form.html'
    success_url = reverse_lazy('warehouses:product_list')
    permission_required = 'warehouses.change_product'

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث المنتج بنجاح.")
        return super().form_valid(form)

class ProductDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Product
    template_name = 'warehouses/product_confirm_delete.html'
    success_url = reverse_lazy('warehouses:product_list')
    permission_required = 'warehouses.delete_product'

    def post(self, request, *args, **kwargs):
        """
        Handles the deletion process and catches ProtectedError if the
        product is in use.
        """
        product_to_delete = self.get_object()
        product_name = product_to_delete.name

        try:
            # Attempt to delete the object
            response = super().post(request, *args, **kwargs)
            messages.success(request, f"تم حذف المنتج '{product_name}' بنجاح.")
            return response
        except ProtectedError:
            # If deletion is blocked, show an informative error message and redirect
            messages.error(
                request,
                f"لا يمكن حذف المنتج '{product_name}' لأنه مستخدم في سجلات أخرى (مثل قوائم المواد 'BOMs'). يرجى إزالة المنتج من تلك السجلات أولاً."
            )
            return redirect('warehouses:product_list')
class ProductSearchView(LoginRequiredMixin, View):
    def get(self, request):
        search = request.GET.get('q', '')
        products = Product.objects.filter(
            Q(name__icontains=search) | Q(code__icontains=search) | Q(barcode__icontains=search)
        ).select_related('category')[:10]
        
        data = [{
            'id': prod.id, 
            'name': prod.name, 
            'code': prod.code,
            'unit': prod.get_unit_display()
        } for prod in products]
        return JsonResponse({'products': data})

class ProductBarcodeView(LoginRequiredMixin, View):
    def get(self, request, barcode):
        try:
            product = Product.objects.get(barcode=barcode)
            data = {
                'id': product.id,
                'name': product.name,
                'code': product.code,
                'unit': product.get_unit_display(),
                'cost_price': str(product.cost_price),
                'selling_price': str(product.selling_price)
            }
            return JsonResponse({'product': data})
        except Product.DoesNotExist:
            return JsonResponse({'error': 'المنتج غير موجود'}, status=404)

# Warehouses
# Update the WarehouseListView in your existing warehouses/views.py file

class WarehouseListView(LoginRequiredMixin,PermissionRequiredMixin, ListView):
    model = Warehouse
    template_name = 'warehouses/warehouse_list.html'
    context_object_name = 'warehouses'
    paginate_by = 12 # Adjusted for card layout
    permission_required = 'warehouses.view_warehouse'
    
    def get_queryset(self):
        queryset = Warehouse.objects.select_related('manager').all()
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(code__icontains=search)
            )
        
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
            
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_warehouses = Warehouse.objects.all()
        context.update({
            'total_warehouses': all_warehouses.count(),
            'active_warehouses': all_warehouses.filter(is_active=True).count(),
            'inactive_warehouses': all_warehouses.filter(is_active=False).count(),
        })
        return context

class WarehouseCreateView(CreateView ,LoginRequiredMixin, PermissionRequiredMixin):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'warehouses/warehouse_form.html'
    success_url = reverse_lazy('warehouses:warehouse_list')
    permission_required = 'warehouses.add_warehouse'

    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء المخزن بنجاح.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'إنشاء مخزن جديد'
        return context

class WarehouseDetailView(DetailView ,LoginRequiredMixin, PermissionRequiredMixin):
    model = Warehouse
    template_name = 'warehouses/warehouse_detail.html'
    context_object_name = 'warehouse'
    permission_required = 'warehouses.view_warehouse'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warehouse = self.get_object()
        all_stock_items = StockItem.objects.filter(warehouse=warehouse).select_related('product')
        active_stock_items = all_stock_items.filter(quantity__gt=0)
        total_value = sum(item.total_value for item in all_stock_items)
        low_stock_count = 0
        for item in active_stock_items:
            if item.is_low_stock:
                low_stock_count += 1
        active_items_count = active_stock_items.count()
        normal_stock_count = active_items_count - low_stock_count
        context['stock_items'] = active_stock_items
        context['total_stock_items_count'] = active_items_count
        context['total_value'] = total_value
        context['low_stock_count'] = low_stock_count
        context['normal_stock_count'] = normal_stock_count
        return context

class WarehouseUpdateView(UpdateView ,LoginRequiredMixin, PermissionRequiredMixin):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'warehouses/warehouse_form.html'
    success_url = reverse_lazy('warehouses:warehouse_list')
    permission_required = 'warehouses.change_warehouse'

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث المخزن بنجاح.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'تعديل المخزن'
        return context

# --- FIX: Added the missing WarehouseDeleteView ---
class WarehouseDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Warehouse
    template_name = 'warehouses/warehouse_confirm_delete.html'
    success_url = reverse_lazy('warehouses:warehouse_list')
    permission_required = 'warehouses.delete_warehouse'

    def post(self, request, *args, **kwargs):
        # Add a success message before deleting the object
        messages.success(self.request, f"تم حذف المخزن '{self.get_object().name}' بنجاح.")
        return super().post(request, *args, **kwargs)


class WarehouseSearchView(LoginRequiredMixin, View):
    def get(self, request):
        search = request.GET.get('q', '')
        warehouses = Warehouse.objects.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )[:10]
        
        data = [{'id': wh.id, 'name': wh.name, 'code': wh.code} for wh in warehouses]
        return JsonResponse({'warehouses': data})

# Stock
from django.db.models import Sum, F, DecimalField, Value
from django.db.models.functions import Coalesce, Cast

class StockListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StockItem
    template_name = 'warehouses/stock_list.html'
    context_object_name = 'stock_items'
    paginate_by = 25
    permission_required = 'warehouses.view_stockitem'
    
    def get_queryset(self):
        queryset = StockItem.objects.select_related('product', 'warehouse', 'product__category')
        
        # Search functionality
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search) |
                Q(product__code__icontains=search) |
                Q(warehouse__name__icontains=search) |
                Q(location__icontains=search)
            )
        
        # Filter by warehouse
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(product__category_id=category_id)
        
        return queryset.order_by('product__name')
    
    # Replace the get_context_data method in StockListView (around line 280)
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        context['categories'] = Category.objects.filter(is_active=True)
        
        # Get all stock items for statistics (apply same filters as main queryset)
        all_stock_items = StockItem.objects.select_related('product')
        
        # Apply same filters as main queryset
        search = self.request.GET.get('search')
        if search:
            all_stock_items = all_stock_items.filter(
                Q(product__name__icontains=search) |
                Q(product__code__icontains=search) |
                Q(warehouse__name__icontains=search) |
                Q(location__icontains=search)
            )
        
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            all_stock_items = all_stock_items.filter(warehouse_id=warehouse_id)
        
        category_id = self.request.GET.get('category')
        if category_id:
            all_stock_items = all_stock_items.filter(product__category_id=category_id)
        
        # Calculate statistics
        context['total_items'] = all_stock_items.count()
        context['low_stock_count'] = all_stock_items.filter(
            quantity__lte=F('product__min_stock_level'),
            quantity__gt=0
        ).count()
        context['out_of_stock_count'] = all_stock_items.filter(quantity=0).count()
        
        # Calculate total value using Python (more reliable)
        total_value = 0
        for item in all_stock_items:
            try:
                item_value = float(item.quantity) * float(item.product.cost_price)
                total_value += item_value
            except (ValueError, TypeError):
                continue
        
        context['total_value'] = total_value
        
        return context


class StockCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    template_name = 'warehouses/stock_form.html'
    permission_required = 'warehouses.add_stockitem'    
    def get(self, request):
        from django import forms
        
        class StockForm(forms.Form):
            warehouse = forms.ModelChoiceField(
                queryset=Warehouse.objects.filter(is_active=True),
                empty_label="اختر المخزن",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            product = forms.ModelChoiceField(
                queryset=Product.objects.filter(is_active=True),
                empty_label="اختر المنتج",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            quantity = forms.DecimalField(
                min_value=0.01,
                decimal_places=2,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
            )
            location = forms.CharField(
                required=False,
                max_length=100,
                widget=forms.TextInput(attrs={'class': 'form-control'})
            )
        
        form = StockForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        # Log the request to debug double submission
        logger.info(f"Stock creation request from user: {request.user.username}")
        
        from django import forms
        
        class StockForm(forms.Form):
            warehouse = forms.ModelChoiceField(
                queryset=Warehouse.objects.filter(is_active=True),
                empty_label="اختر المخزن",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            product = forms.ModelChoiceField(
                queryset=Product.objects.filter(is_active=True),
                empty_label="اختر المنتج",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            quantity = forms.DecimalField(
                min_value=0.01,
                decimal_places=2,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
            )
            location = forms.CharField(
                required=False,
                max_length=100,
                widget=forms.TextInput(attrs={'class': 'form-control'})
            )
        
        form = StockForm(request.POST)
        
        if form.is_valid():
            warehouse = form.cleaned_data['warehouse']
            product = form.cleaned_data['product']
            quantity = form.cleaned_data['quantity']
            location = form.cleaned_data.get('location', '')
            
            logger.info(f"Adding {quantity} of {product.name} to {warehouse.name}")
            
            try:
                # Use get_or_create to handle race conditions
                existing_stock, created = StockItem.objects.get_or_create(
                    warehouse=warehouse,
                    product=product,
                    defaults={
                        'quantity': 0,  # Start with 0, signal will update
                        'location': location
                    }
                )
                
                if created:
                    # New stock item created
                    logger.info(f"Created new stock item")
                    
                    # Create initial stock movement - signal will handle quantity update
                    StockMovement.objects.create(
                        stock_item=existing_stock,
                        movement_type='in',
                        quantity=quantity,
                        reference_number=f'NEW-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                        notes='إنشاء مخزون جديد',
                        created_by=request.user
                    )
                    
                    messages.success(request, f'تم إنشاء عنصر مخزون جديد بكمية {quantity} {product.get_unit_display()}')
                    
                else:
                    # Stock item already exists
                    old_quantity = existing_stock.quantity
                    if location:
                        existing_stock.location = location
                        existing_stock.save()
                    
                    logger.info(f"Adding to existing stock. Current quantity: {old_quantity}")
                    
                    # Create stock movement record - signal will handle quantity update
                    StockMovement.objects.create(
                        stock_item=existing_stock,
                        movement_type='in',
                        quantity=quantity,
                        reference_number=f'ADD-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                        notes=f'إضافة مخزون. الكمية السابقة: {old_quantity}',
                        created_by=request.user
                    )
                    
                    # Refresh to get updated quantity from signal
                    existing_stock.refresh_from_db()
                    
                    messages.success(
                        request, 
                        f'تم إضافة {quantity} {product.get_unit_display()} إلى المخزون الموجود. الكمية الجديدة: {existing_stock.quantity}'
                    )
                
                return redirect('warehouses:stock_list')
                
            except Exception as e:
                logger.error(f"Error in stock creation: {str(e)}")
                messages.error(request, f'حدث خطأ: {str(e)}')
                return render(request, self.template_name, {'form': form})
        
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء المذكورة.')
            return render(request, self.template_name, {'form': form})




class CheckExistingStockView(LoginRequiredMixin, View):
    """Check if stock item already exists for warehouse and product combination"""
    
    def get(self, request):
        warehouse_id = request.GET.get('warehouse')
        product_id = request.GET.get('product')
        
        if not warehouse_id or not product_id:
            return JsonResponse({'exists': False})
        
        try:
            existing_stock = StockItem.objects.select_related('product').get(
                warehouse_id=warehouse_id,
                product_id=product_id
            )
            
            return JsonResponse({
                'exists': True,
                'current_quantity': float(existing_stock.quantity),
                'unit': existing_stock.product.get_unit_display(),
                'location': existing_stock.location or ''
            })
            
        except StockItem.DoesNotExist:
            return JsonResponse({'exists': False})
        except Exception as e:
            return JsonResponse({'exists': False, 'error': str(e)})

class StockDetailView(LoginRequiredMixin, DetailView):
    model = StockItem
    template_name = 'warehouses/stock_detail.html'
    context_object_name = 'stock_item'
    permission_required = 'warehouses.view_stockitem'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_movements'] = self.object.movements.all()[:10]
        return context


class InventoryCountView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    A professional view for performing a full inventory count (جرد المخزون).
    """
    template_name = 'warehouses/inventory_count.html'
    permission_required = 'warehouses.change_stockitem'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warehouse_id = self.request.GET.get('warehouse')
        
        if warehouse_id:
            try:
                # Ensure the warehouse_id is a valid integer before querying
                warehouse = get_object_or_404(Warehouse, id=int(warehouse_id))
                stock_items = StockItem.objects.filter(
                    warehouse=warehouse
                ).select_related('product').order_by('product__name')
                
                context.update({
                    'selected_warehouse': warehouse,
                    'stock_items': stock_items
                })
            except (ValueError, TypeError):
                messages.error(self.request, "معرف المخزن المحدد غير صالح.")
            except Warehouse.DoesNotExist:
                messages.error(self.request, "المخزن المحدد غير موجود.")
        
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        return context
    
    def post(self, request, *args, **kwargs):
        """
        Processes the submitted stock count form with improved error handling.
        """
        # --- FIX: Get the warehouse_id from the hidden input ---
        warehouse_id = request.POST.get('warehouse_id')
        
        if not warehouse_id:
            messages.error(request, 'حدث خطأ: لم يتم تحديد المخزن. يرجى إعادة المحاولة.')
            return redirect('warehouses:inventory_count')

        try:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
            adjustments_made = 0
            
            # Iterate through all POST data to find submitted quantities
            for key, counted_quantity_str in request.POST.items():
                if key.startswith('quantity_'):
                    stock_item_id = key.split('_')[1]
                    
                    # Skip items where the quantity was not entered or is empty
                    if not counted_quantity_str:
                        continue
                        
                    # Ensure the stock item belongs to the correct warehouse to prevent mix-ups
                    stock_item = get_object_or_404(StockItem, id=stock_item_id, warehouse=warehouse)
                    counted_quantity = Decimal(counted_quantity_str)
                    
                    # Only create a movement if the quantity has actually changed
                    if stock_item.quantity != counted_quantity:
                        old_quantity = stock_item.quantity
                        
                        # The signal on StockMovement handles the actual quantity update.
                        # For 'adjustment' type, the quantity field represents the NEW total.
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type='adjustment',
                            quantity=counted_quantity,
                            notes=f'جرد مخزون لمخزن {warehouse.name}. الكمية السابقة: {old_quantity}',
                            created_by=request.user
                        )
                        adjustments_made += 1
            
            if adjustments_made > 0:
                messages.success(
                    request, 
                    f'تم حفظ نتائج الجرد لمخزن "{warehouse.name}" بنجاح. تم إجراء {adjustments_made} تسوية.'
                )
            else:
                messages.info(request, "لم يتم إجراء أي تغييرات حيث أن جميع الكميات كانت متطابقة.")
            
        except (ValueError, TypeError):
             messages.error(request, 'معرف المخزن المحدد غير صالح.')
        except Warehouse.DoesNotExist:
             messages.error(request, 'المخزن الذي تحاول الجرد له غير موجود.')
        except StockItem.DoesNotExist:
             messages.error(request, 'تم العثور على عنصر مخزون غير صالح في الطلب. قد يكون تم حذفه.')
        except Exception as e:
            messages.error(request, f'حدث خطأ غير متوقع أثناء حفظ الجرد: {str(e)}')
        
        # Redirect back to the same page to show the results/messages
        return redirect(f"{reverse('warehouses:inventory_count')}?warehouse={warehouse_id}")

class StockUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = StockItem
    # Use the new, specific update form
    form_class = StockItemUpdateForm
    template_name = 'warehouses/stock_form.html'
    success_url = reverse_lazy('warehouses:stock_list')
    permission_required = 'warehouses.change_stockitem'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the object to the template for display purposes
        context['object'] = self.get_object()
        return context

    def form_valid(self, form):
        messages.success(self.request, f'تم تحديث مخزون المنتج "{self.object.product.name}" بنجاح.')
        return super().form_valid(form)

class StockSearchView(LoginRequiredMixin, View):
    def get(self, request):
        search = request.GET.get('q', '')
        stock_items = StockItem.objects.filter(
            Q(product__name__icontains=search) | Q(product__code__icontains=search)
        ).select_related('product', 'warehouse')[:10]
        
        data = [{
            'id': item.id,
            'product_name': item.product.name,
            'warehouse_name': item.warehouse.name,
            'quantity': str(item.quantity)
        } for item in stock_items]
        return JsonResponse({'stock_items': data})

class LowStockView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'warehouses/low_stock.html'
    context_object_name = 'stock_items'
    paginate_by = 25
    permission_required = 'warehouses.view_stockitem'
    
    def get_queryset(self):
        return StockItem.objects.filter(
            quantity__lte=F('product__min_stock_level')
        ).select_related('product', 'warehouse').order_by('quantity')


class LowStockPDFView(LoginRequiredMixin, View):
    """
    Generates a PDF report for all low stock items.
    """
    def get(self, request, *args, **kwargs):
        low_stock_items = StockItem.objects.filter(
            quantity__lte=F('product__min_stock_level'),
            quantity__gt=0
        ).select_related('product', 'warehouse').order_by('product__name')

        context = {
            'stock_items': low_stock_items,
            'timestamp': timezone.now(),
        }

        html_string = render_to_string('pdf/warehouses/low_stock_pdf.html', context)
        
        try:
            config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
            pdf = pdfkit.from_string(html_string, False, configuration=config, options={"enable-local-file-access": ""})
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="low_stock_report.pdf"'
            return response
        except FileNotFoundError:
            messages.error(request, "Could not generate PDF. wkhtmltopdf executable not found.")
            return redirect('warehouses:low_stock')
        except Exception as e:
            messages.error(request, f"An unexpected error occurred while generating the PDF: {e}")
            return redirect('warehouses:low_stock')


class StockItemDetailPDFView(LoginRequiredMixin, View):
    """
    Generates a PDF report for a single StockItem.
    """
    def get(self, request, *args, **kwargs):
        stock_item = get_object_or_404(StockItem, pk=self.kwargs['pk'])
        recent_movements = stock_item.movements.all().select_related('created_by')[:20]

        context = {
            'stock_item': stock_item,
            'recent_movements': recent_movements,
            'timestamp': timezone.now(),
        }

        # Render the PDF template to a string
        html_string = render_to_string('pdf/warehouses/stock_item_detail_pdf.html', context)
        
        try:
            # IMPORTANT: Ensure WKHTMLTOPDF_PATH is set correctly in your settings.py
            config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
            
            pdf = pdfkit.from_string(html_string, False, configuration=config, options={"enable-local-file-access": ""})

            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="stock_item_report_{stock_item.product.code}.pdf"'
            
            return response
            
        except FileNotFoundError:
            messages.error(request, "Could not generate PDF. wkhtmltopdf executable not found.")
            return redirect('warehouses:stock_detail', pk=stock_item.pk)
        except Exception as e:
            messages.error(request, f"An unexpected error occurred while generating the PDF: {e}")
            return redirect('warehouses:stock_detail', pk=stock_item.pk)


class OutOfStockView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'warehouses/out_of_stock.html'
    context_object_name = 'stock_items'
    paginate_by = 25
    permission_required = 'warehouses.view_stockitem'
    def get_queryset(self):
        return StockItem.objects.filter(
            quantity=0
        ).select_related('product', 'warehouse').order_by('product__name')

# Add these views to the existing warehouses/views.py file

# Stock Movements
class StockMovementListView(LoginRequiredMixin, ListView):
    model = StockMovement
    template_name = 'warehouses/movement_list.html'
    context_object_name = 'movements'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = StockMovement.objects.select_related('stock_item__product', 'stock_item__warehouse', 'created_by').all()
        
        # البحث
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(stock_item__product__name__icontains=search) |
                Q(stock_item__warehouse__name__icontains=search) |
                Q(reference_number__icontains=search)
            )
        
        # فلترة حسب نوع الحركة
        movement_type = self.request.GET.get('movement_type')
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        
        # فلترة حسب المخزن
        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            queryset = queryset.filter(stock_item__warehouse_id=warehouse)
        
        # فلترة حسب التاريخ
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['movement_types'] = StockMovement.MOVEMENT_TYPES
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        context['filters'] = {
            'search': self.request.GET.get('search', ''),
            'movement_type': self.request.GET.get('movement_type', ''),
            'warehouse': self.request.GET.get('warehouse', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context


class StockMovementCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StockMovement
    template_name = 'warehouses/movement_form.html'
    fields = ['stock_item', 'movement_type', 'quantity', 'reference_number', 'notes']
    success_url = reverse_lazy('warehouses:movement_list')
    permission_required = 'warehouses.add_stockmovement'
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # تحديث كمية المخزون
        stock_item = form.instance.stock_item
        if form.instance.movement_type == 'in':
            stock_item.quantity += form.instance.quantity
        elif form.instance.movement_type == 'out':
            if stock_item.quantity >= form.instance.quantity:
                stock_item.quantity -= form.instance.quantity
            else:
                messages.error(self.request, 'الكمية المطلوبة غير متوفرة في المخزون')
                return self.form_invalid(form)
        elif form.instance.movement_type == 'adjustment':
            stock_item.quantity = form.instance.quantity
        
        stock_item.save()
        messages.success(self.request, 'تم إنشاء حركة المخزون بنجاح')
        return response


class StockMovementDetailView(LoginRequiredMixin,PermissionRequiredMixin, DetailView):
    model = StockMovement
    template_name = 'warehouses/movement_detail.html'
    context_object_name = 'movement'
    permission_required = 'warehouses.view_stockmovement'



# Stock Transfers
class StockTransferListView(LoginRequiredMixin, ListView):
    model = StockTransfer
    template_name = 'warehouses/transfer_list.html'
    context_object_name = 'transfers'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = StockTransfer.objects.select_related(
            'from_warehouse', 'to_warehouse', 'product', 'requested_by'
        ).all()
        
        # البحث
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(transfer_number__icontains=search) |
                Q(product__name__icontains=search) |
                Q(from_warehouse__name__icontains=search) |
                Q(to_warehouse__name__icontains=search)
            )
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # فلترة حسب المخزن
        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            queryset = queryset.filter(
                Q(from_warehouse_id=warehouse) | Q(to_warehouse_id=warehouse)
            )
        
        return queryset.order_by('-requested_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = StockTransfer.TRANSFER_STATUS
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        context['filters'] = {
            'search': self.request.GET.get('search', ''),
            'status': self.request.GET.get('status', ''),
            'warehouse': self.request.GET.get('warehouse', ''),
        }
        return context


class StockTransferCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StockTransfer
    template_name = 'warehouses/transfer_form.html'
    fields = ['from_warehouse', 'to_warehouse', 'product', 'quantity', 'reason']
    success_url = reverse_lazy('warehouses:transfer_list')
    permission_required = 'warehouses.add_stocktransfer'    
    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        
        # توليد رقم التحويل
        today = timezone.now().date()
        prefix = f"TR{today.strftime('%Y%m%d')}"
        last_transfer = StockTransfer.objects.filter(
            transfer_number__startswith=prefix
        ).order_by('-transfer_number').first()
        
        if last_transfer:
            last_number = int(last_transfer.transfer_number[-4:])
            new_number = last_number + 1
        else:
            new_number = 1
        
        form.instance.transfer_number = f"{prefix}{new_number:04d}"
        
        # التحقق من توفر الكمية
        try:
            stock_item = StockItem.objects.get(
                warehouse=form.instance.from_warehouse,
                product=form.instance.product
            )
            if stock_item.available_quantity < form.instance.quantity:
                messages.error(self.request, 'الكمية المطلوبة غير متوفرة في المخزن المصدر')
                return self.form_invalid(form)
        except StockItem.DoesNotExist:
            messages.error(self.request, 'المنتج غير موجود في المخزن المصدر')
            return self.form_invalid(form)
        
        messages.success(self.request, 'تم إنشاء طلب التحويل بنجاح')
        return super().form_valid(form)


class StockTransferDetailView(LoginRequiredMixin, DetailView):
    model = StockTransfer
    template_name = 'warehouses/transfer_detail.html'
    context_object_name = 'transfer'


class StockTransferApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'warehouses.change_stocktransfer'    
    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, pk=pk)
        
        if transfer.status != 'pending':
            messages.error(request, 'لا يمكن الموافقة على هذا التحويل')
            return redirect('warehouses:transfer_detail', pk=pk)
        
        # التحقق من توفر الكمية مرة أخرى
        try:
            stock_item = StockItem.objects.get(
                warehouse=transfer.from_warehouse,
                product=transfer.product
            )
            if stock_item.available_quantity < transfer.quantity:
                messages.error(request, 'الكمية المطلوبة غير متوفرة في المخزن المصدر')
                return redirect('warehouses:transfer_detail', pk=pk)
        except StockItem.DoesNotExist:
            messages.error(request, 'المنتج غير موجود في المخزن المصدر')
            return redirect('warehouses:transfer_detail', pk=pk)
        
        # حجز الكمية
        stock_item.reserved_quantity += transfer.quantity
        stock_item.save()
        
        # تحديث حالة التحويل
        transfer.status = 'approved'
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()
        
        messages.success(request, 'تم الموافقة على التحويل بنجاح')
        return redirect('warehouses:transfer_detail', pk=pk)


class StockTransferCompleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'warehouses.change_stocktransfer'    
    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, pk=pk)
        
        if transfer.status != 'approved':
            messages.error(request, 'لا يمكن إكمال هذا التحويل')
            return redirect('warehouses:transfer_detail', pk=pk)
        
        try:
            # تحديث المخزن المصدر
            from_stock = StockItem.objects.get(
                warehouse=transfer.from_warehouse,
                product=transfer.product
            )
            from_stock.quantity -= transfer.quantity
            from_stock.reserved_quantity -= transfer.quantity
            from_stock.save()
            
            # إنشاء حركة صادر
            StockMovement.objects.create(
                stock_item=from_stock,
                movement_type='transfer',
                quantity=-transfer.quantity,
                reference_number=transfer.transfer_number,
                notes=f'تحويل إلى {transfer.to_warehouse.name}',
                created_by=request.user
            )
            
            # تحديث المخزن المستقبل
            to_stock, created = StockItem.objects.get_or_create(
                warehouse=transfer.to_warehouse,
                product=transfer.product,
                defaults={'quantity': 0}
            )
            to_stock.quantity += transfer.quantity
            to_stock.save()
            
            # إنشاء حركة وارد
            StockMovement.objects.create(
                stock_item=to_stock,
                movement_type='transfer',
                quantity=transfer.quantity,
                reference_number=transfer.transfer_number,
                notes=f'تحويل من {transfer.from_warehouse.name}',
                created_by=request.user
            )
            
            # تحديث حالة التحويل
            transfer.status = 'completed'
            transfer.completed_by = request.user
            transfer.completed_at = timezone.now()
            transfer.save()
            
            messages.success(request, 'تم إكمال التحويل بنجاح')
            
        except StockItem.DoesNotExist:
            messages.error(request, 'خطأ في بيانات المخزون')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('warehouses:transfer_detail', pk=pk)


# Additional utility views
class StockAdjustmentView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    A view for performing stock adjustments for a selected warehouse.
    Handles both displaying the stock items and processing the adjustments.
    """
    template_name = 'warehouses/stock_adjustment.html'
    permission_required = 'warehouses.change_stockitem'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warehouse_id = self.request.GET.get('warehouse')
        
        # Populate the list of all warehouses for the dropdown
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        
        if warehouse_id:
            try:
                # Get the selected warehouse and its stock items
                warehouse = get_object_or_404(Warehouse, id=int(warehouse_id))
                stock_items = StockItem.objects.filter(
                    warehouse=warehouse
                ).select_related('product', 'product__unit_new').order_by('product__name')
                
                context.update({
                    'selected_warehouse': warehouse,
                    'stock_items': stock_items
                })
            except (ValueError, TypeError):
                messages.error(self.request, "معرف المخزن المحدد غير صالح.")
            except Warehouse.DoesNotExist:
                messages.error(self.request, "المخزن المحدد غير موجود.")
        
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Processes the submitted stock adjustment form.
        """
        warehouse_id = request.POST.get('warehouse_id')
        
        if not warehouse_id:
            messages.error(request, 'حدث خطأ: لم يتم تحديد المخزن. يرجى إعادة المحاولة.')
            return redirect('warehouses:stock_adjustment')

        try:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
            adjustments_made = 0
            
            # Iterate through all POST data to find submitted quantities
            for key, quantity_str in request.POST.items():
                if key.startswith('quantity_') and quantity_str:
                    try:
                        stock_item_id = key.split('_')[1]
                        adjustment_quantity = Decimal(quantity_str)
                        
                        # Get corresponding movement type and notes
                        movement_type = request.POST.get(f'movement_type_{stock_item_id}')
                        notes = request.POST.get(f'notes_{stock_item_id}', '')

                        # Get the stock item, ensuring it belongs to the correct warehouse
                        stock_item = get_object_or_404(StockItem, id=stock_item_id, warehouse=warehouse)
                        
                        # Skip if quantity is zero or movement type is not selected
                        if adjustment_quantity <= 0 or not movement_type:
                            continue

                        # The signal on StockMovement will handle the actual quantity update.
                        # We just need to create the movement record with the correct data.
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type=movement_type,
                            quantity=adjustment_quantity,
                            notes=f"تسوية يدوية: {notes}",
                            reference_number=f'ADJ-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                            created_by=request.user
                        )
                        adjustments_made += 1
                        
                    except (InvalidOperation, ValueError):
                        messages.warning(request, f"تم تخطي عنصر بقيمة كمية غير صالحة: '{quantity_str}'.")
                        continue
                    except StockItem.DoesNotExist:
                        messages.warning(request, f"تم تخطي عنصر مخزون غير موجود بالمعرف: {stock_item_id}.")
                        continue

            if adjustments_made > 0:
                messages.success(
                    request, 
                    f'تم حفظ التسويات لمخزن "{warehouse.name}" بنجاح. تم إجراء {adjustments_made} حركة.'
                )
            else:
                messages.info(request, "لم يتم إدخال أي كميات للتسوية.")
            
        except Warehouse.DoesNotExist:
             messages.error(request, 'المخزن الذي تحاول التسوية له غير موجود.')
        except Exception as e:
            # Catch any other unexpected errors and report them
            messages.error(request, f'حدث خطأ غير متوقع أثناء حفظ التسويات: {str(e)}')
        
        # Redirect back to the same page (with the warehouse parameter) to show results
        return redirect(f"{reverse('warehouses:stock_adjustment')}?warehouse={warehouse_id}")


class StockReportView(LoginRequiredMixin, TemplateView):
    """تقارير المخزون"""
    template_name = 'warehouses/stock_reports.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # فترة التقرير
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        warehouse_id = self.request.GET.get('warehouse')
        
        if not date_from:
            date_from = (timezone.now() - timedelta(days=30)).date()
        else:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            
        if not date_to:
            date_to = timezone.now().date()
        else:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        
        # فلترة حسب المخزن
        movements_query = StockMovement.objects.filter(
            created_at__date__range=[date_from, date_to]
        )
        
        if warehouse_id:
            movements_query = movements_query.filter(stock_item__warehouse_id=warehouse_id)
        
        # إحصائيات الحركات
        movements_stats = movements_query.aggregate(
            total_in=Sum('quantity', filter=Q(movement_type='in')),
            total_out=Sum('quantity', filter=Q(movement_type__in=['out', 'transfer'])),
            total_adjustments=Count('id', filter=Q(movement_type='adjustment'))
        )
        
        # المنتجات منخفضة المخزون
        low_stock_query = StockItem.objects.filter(
            quantity__lte=F('product__min_stock_level')
        ).select_related('product', 'warehouse')
        
        if warehouse_id:
            low_stock_query = low_stock_query.filter(warehouse_id=warehouse_id)
        
        # المنتجات الأكثر حركة
        top_products = StockMovement.objects.filter(
            created_at__date__range=[date_from, date_to]
        ).values(
            'stock_item__product__name'
        ).annotate(
            total_movements=Count('id'),
            total_quantity=Sum('quantity')
        ).order_by('-total_movements')[:10]
        
        context.update({
            'date_from': date_from,
            'date_to': date_to,
            'warehouse_id': warehouse_id,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'movements_stats': movements_stats,
            'low_stock_items': low_stock_query[:20],
            'top_products': top_products,
            'recent_movements': movements_query.select_related(
                'stock_item__product', 'stock_item__warehouse', 'created_by'
            )[:20]
        })
        
        return context




# API Views for AJAX requests
from django.http import JsonResponse
from django.views import View

# Add this API view for product stock information
class ProductStockAPIView(LoginRequiredMixin, View):
    def get(self, request, product_id):
        try:
            product = get_object_or_404(Product, id=product_id)
            
            # Get stock items for this product
            stock_items = StockItem.objects.filter(product=product).select_related('warehouse')
            
            stock_data = []
            for item in stock_items:
                stock_data.append({
                    'warehouse_id': item.warehouse.id,
                    'warehouse_name': item.warehouse.name,
                    'quantity': float(item.quantity),
                    'available_quantity': float(item.available_quantity),
                    'reserved_quantity': float(item.reserved_quantity),
                    'location': item.location or '',
                    'is_low_stock': item.is_low_stock
                })
            
            return JsonResponse({
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'code': product.code,
                    'unit': product.unit,
                    'unit_display': product.get_unit_display(),
                    'min_stock_level': product.min_stock_level,
                    'cost_price': float(product.cost_price),
                    'selling_price': float(product.selling_price),
                    'product_type': product.product_type,
                    'product_type_display': product.get_product_type_display(),
                },
                'stock_items': stock_data,
                'total_stock': sum(item['quantity'] for item in stock_data)
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


class WarehouseStockAPIView(LoginRequiredMixin, View):
    """API للحصول على معلومات مخزون المخزن"""
    
    def get(self, request, warehouse_id):
        try:
            warehouse = Warehouse.objects.get(id=warehouse_id)
            stock_items = StockItem.objects.filter(
                warehouse=warehouse
            ).select_related('product')
            
            # إحصائيات المخزن
            stats = {
                'total_products': stock_items.count(),
                'low_stock_items': stock_items.filter(
                    quantity__lte=F('product__min_stock_level')
                ).count(),
                'out_of_stock_items': stock_items.filter(quantity=0).count(),
                'total_value': sum(
                    item.quantity * item.product.cost_price 
                    for item in stock_items
                )
            }
            
            # المنتجات
            products_data = [{
                'product_id': item.product.id,
                'product_name': item.product.name,
                'product_code': item.product.code,
                'quantity': float(item.quantity),
                'available_quantity': float(item.available_quantity),
                'reserved_quantity': float(item.reserved_quantity),
                'unit': item.product.get_unit_display(),
                'cost_price': float(item.product.cost_price),
                'total_value': float(item.quantity * item.product.cost_price),
                'location': item.location,
                'is_low_stock': item.is_low_stock
            } for item in stock_items]
            
            data = {
                'warehouse': {
                    'id': warehouse.id,
                    'name': warehouse.name,
                    'code': warehouse.code
                },
                'stats': stats,
                'products': products_data
            }
            
            return JsonResponse(data)
            
        except Warehouse.DoesNotExist:
            return JsonResponse({'error': 'المخزن غير موجود'}, status=404)


# Export Views
@login_required
def export_stock_csv(request):
    """تصدير المخزون إلى CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stock_report.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'المخزن', 'كود المخزن', 'المنتج', 'كود المنتج', 'الكمية',
        'الكمية المتاحة', 'الكمية المحجوزة', 'الوحدة', 'الموقع',
        'سعر التكلفة', 'القيمة الإجمالية', 'الحد الأدنى', 'حالة المخزون'
    ])
    
    warehouse_id = request.GET.get('warehouse')
    stock_items = StockItem.objects.select_related('product', 'warehouse').all()
    
    if warehouse_id:
        stock_items = stock_items.filter(warehouse_id=warehouse_id)
    
    for item in stock_items:
        status = 'نفد' if item.quantity == 0 else ('منخفض' if item.is_low_stock else 'طبيعي')
        
        writer.writerow([
            item.warehouse.name,
            item.warehouse.code,
            item.product.name,
            item.product.code,
            float(item.quantity),
            float(item.available_quantity),
            float(item.reserved_quantity),
            item.product.get_unit_display(),
            item.location,
            float(item.product.cost_price),
            float(item.quantity * item.product.cost_price),
            item.product.min_stock_level,
            status
        ])
    
    return response


@login_required
def export_movements_csv(request):
    """تصدير حركات المخزون إلى CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stock_movements.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'التاريخ', 'المخزن', 'المنتج', 'نوع الحركة', 'الكمية',
        'رقم المرجع', 'ملاحظات', 'المستخدم'
    ])
    
    # فلترة حسب التاريخ
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    movements = StockMovement.objects.select_related(
        'stock_item__product', 'stock_item__warehouse', 'created_by'
    ).all()
    
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
    
    for movement in movements:
        writer.writerow([
            movement.created_at.strftime('%Y-%m-%d %H:%M'),
            movement.stock_item.warehouse.name,
            movement.stock_item.product.name,
            movement.get_movement_type_display(),
            float(movement.quantity),
            movement.reference_number,
            movement.notes,
            movement.created_by.username if movement.created_by else ''
        ])
    
    return response


# Bulk Operations
@login_required
@require_http_methods(["POST"])
def bulk_stock_update(request):
    """تحديث مجموعي للمخزون"""
    stock_item_ids = request.POST.getlist('stock_item_ids')
    action = request.POST.get('action')
    
    if not stock_item_ids or not action:
        return JsonResponse({'success': False, 'error': 'بيانات غير مكتملة'})
    
    stock_items = StockItem.objects.filter(id__in=stock_item_ids)
    
    try:
        if action == 'adjust_location':
            new_location = request.POST.get('new_location', '')
            stock_items.update(location=new_location)
            message = f'تم تحديث موقع {stock_items.count()} عنصر'
            
        elif action == 'reserve_quantity':
            reserve_quantity = float(request.POST.get('reserve_quantity', 0))
            for item in stock_items:
                if item.available_quantity >= reserve_quantity:
                    item.reserved_quantity += reserve_quantity
                    item.save()
            message = f'تم حجز الكمية لـ {stock_items.count()} عنصر'
            
        elif action == 'release_reserved':
            stock_items.update(reserved_quantity=0)
            message = f'تم إلغاء حجز الكمية لـ {stock_items.count()} عنصر'
            
        else:
            return JsonResponse({'success': False, 'error': 'عملية غير صحيحة'})
        
        return JsonResponse({'success': True, 'message': message})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# Dashboard API
@login_required
def warehouse_dashboard_api(request):
    """API لبيانات لوحة التحكم"""
    
    # إحصائيات عامة
    stats = {
        'total_warehouses': Warehouse.objects.filter(is_active=True).count(),
        'total_products': Product.objects.filter(is_active=True).count(),
        'total_stock_items': StockItem.objects.count(),
        'low_stock_items': StockItem.objects.filter(
            quantity__lte=F('product__min_stock_level')
        ).count(),
        'out_of_stock_items': StockItem.objects.filter(quantity=0).count(),
        'pending_transfers': StockTransfer.objects.filter(status='pending').count(),
        'total_stock_value': StockItem.objects.aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
    }
    
    # حركات المخزون الأخيرة
    recent_movements = StockMovement.objects.select_related(
        'stock_item__product', 'stock_item__warehouse', 'created_by'
    )[:10]
    
    movements_data = [{
        'id': movement.id,
        'product_name': movement.stock_item.product.name,
        'warehouse_name': movement.stock_item.warehouse.name,
        'movement_type': movement.get_movement_type_display(),
        'quantity': float(movement.quantity),
        'created_at': movement.created_at.strftime('%Y-%m-%d %H:%M'),
        'created_by': movement.created_by.username if movement.created_by else ''
    } for movement in recent_movements]
    
    # المنتجات الأكثر حركة (آخر 30 يوم)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    top_products = StockMovement.objects.filter(
        created_at__gte=thirty_days_ago
    ).values(
        'stock_item__product__name'
    ).annotate(
        total_movements=Count('id'),
        total_quantity=Sum('quantity')
    ).order_by('-total_movements')[:5]
    
    # التحويلات المعلقة
    pending_transfers = StockTransfer.objects.filter(
        status='pending'
    ).select_related(
        'from_warehouse', 'to_warehouse', 'product', 'requested_by'
    )[:5]
    
    transfers_data = [{
        'id': transfer.id,
        'transfer_number': transfer.transfer_number,
        'product_name': transfer.product.name,
        'from_warehouse': transfer.from_warehouse.name,
        'to_warehouse': transfer.to_warehouse.name,
        'quantity': float(transfer.quantity),
        'requested_at': transfer.requested_at.strftime('%Y-%m-%d %H:%M'),
        'requested_by': transfer.requested_by.username
    } for transfer in pending_transfers]
    
    # إحصائيات الحركات (آخر 7 أيام)
    seven_days_ago = timezone.now() - timedelta(days=7)
    daily_movements = []
    
    for i in range(7):
        date = (timezone.now() - timedelta(days=i)).date()
        movements_count = StockMovement.objects.filter(
            created_at__date=date
        ).count()
        daily_movements.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': movements_count
        })
    
    daily_movements.reverse()
    
    return JsonResponse({
        'stats': stats,
        'recent_movements': movements_data,
        'top_products': list(top_products),
        'pending_transfers': transfers_data,
        'daily_movements': daily_movements
    })


# Barcode scanning support
class BarcodeStockView(LoginRequiredMixin, View):
    """معالجة الباركود للمخزون"""
    
    def post(self, request):
        barcode = request.POST.get('barcode')
        warehouse_id = request.POST.get('warehouse_id')
        action = request.POST.get('action')  # 'check', 'in', 'out'
        quantity = request.POST.get('quantity', 1)
        
        try:
            product = Product.objects.get(barcode=barcode)
            warehouse = Warehouse.objects.get(id=warehouse_id)
            
            stock_item, created = StockItem.objects.get_or_create(
                warehouse=warehouse,
                product=product,
                defaults={'quantity': 0}
            )
            
            if action == 'check':
                # فقط عرض معلومات المخزون
                data = {
                    'success': True,
                    'product': {
                        'name': product.name,
                        'code': product.code,
                        'unit': product.get_unit_display()
                    },
                    'stock': {
                        'quantity': float(stock_item.quantity),
                        'available_quantity': float(stock_item.available_quantity),
                        'location': stock_item.location
                    }
                }
                
            elif action == 'in':
                # إدخال مخزون
                quantity = float(quantity)
                stock_item.quantity += quantity
                stock_item.save()
                
                # إنشاء حركة
                StockMovement.objects.create(
                    stock_item=stock_item,
                    movement_type='in',
                    quantity=quantity,
                    reference_number=f'SCAN-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                    notes='إدخال عبر الباركود',
                    created_by=request.user
                )
                
                data = {
                    'success': True,
                    'message': f'تم إدخال {quantity} {product.get_unit_display()} من {product.name}',
                    'new_quantity': float(stock_item.quantity)
                }
                
            elif action == 'out':
                # إخراج مخزون
                quantity = float(quantity)
                if stock_item.available_quantity >= quantity:
                    stock_item.quantity -= quantity
                    stock_item.save()
                    
                    # إنشاء حركة
                    StockMovement.objects.create(
                        stock_item=stock_item,
                        movement_type='out',
                        quantity=-quantity,
                        reference_number=f'SCAN-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                        notes='إخراج عبر الباركود',
                        created_by=request.user
                    )
                    
                    data = {
                        'success': True,
                        'message': f'تم إخراج {quantity} {product.get_unit_display()} من {product.name}',
                        'new_quantity': float(stock_item.quantity)
                    }
                else:
                    data = {
                        'success': False,
                        'error': f'الكمية المتاحة غير كافية. المتاح: {stock_item.available_quantity}'
                    }
            else:
                data = {'success': False, 'error': 'عملية غير صحيحة'}
            
            return JsonResponse(data)
            
        except Product.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'المنتج غير موجود'
            })
        except Warehouse.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'المخزن غير موجود'
            })
        except ValueError:
            return JsonResponse({
                'success': False, 
                'error': 'الكمية يجب أن تكون رقم'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': str(e)
            })


# Stock alerts and notifications
class StockAlertsView(LoginRequiredMixin, TemplateView):
    """تنبيهات المخزون"""
    template_name = 'warehouses/stock_alerts.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # المنتجات منخفضة المخزون
        low_stock_items = StockItem.objects.filter(
            quantity__lte=F('product__min_stock_level'),
            quantity__gt=0
        ).select_related('product', 'warehouse').order_by('quantity')
        
        # المنتجات النافدة
        out_of_stock_items = StockItem.objects.filter(
            quantity=0
        ).select_related('product', 'warehouse').order_by('product__name')
        
        # المنتجات التي لم تتحرك لفترة طويلة (90 يوم)
        ninety_days_ago = timezone.now() - timedelta(days=90)
        slow_moving_items = StockItem.objects.exclude(
            id__in=StockMovement.objects.filter(
                created_at__gte=ninety_days_ago
            ).values_list('stock_item_id', flat=True)
        ).filter(quantity__gt=0).select_related('product', 'warehouse')
        
        # التحويلات المتأخرة
        overdue_transfers = StockTransfer.objects.filter(
            status='approved',
            approved_at__lt=timezone.now() - timedelta(days=7)
        ).select_related('from_warehouse', 'to_warehouse', 'product')
        
        context.update({
            'low_stock_items': low_stock_items,
            'out_of_stock_items': out_of_stock_items,
            'slow_moving_items': slow_moving_items,
            'overdue_transfers': overdue_transfers,
            'alerts_count': {
                'low_stock': low_stock_items.count(),
                'out_of_stock': out_of_stock_items.count(),
                'slow_moving': slow_moving_items.count(),
                'overdue_transfers': overdue_transfers.count()
            }
        })
        
        return context

# Add this view to the existing warehouses/views.py file

# Add these functions to the end of your existing warehouses/views.py file

@login_required
def export_warehouse_csv(request, warehouse_id):
    """تصدير بيانات مخزن محدد إلى CSV"""
    try:
        warehouse = Warehouse.objects.get(id=warehouse_id)
    except Warehouse.DoesNotExist:
        messages.error(request, 'المخزن غير موجود')
        return redirect('warehouses:warehouse_list')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="warehouse_{warehouse.code}_stock.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'المنتج', 'كود المنتج', 'الكمية', 'الكمية المتاحة', 'الكمية المحجوزة',
        'الوحدة', 'الموقع', 'سعر التكلفة', 'القيمة الإجمالية', 'الحد الأدنى', 'حالة المخزون'
    ])
    
    stock_items = StockItem.objects.filter(warehouse=warehouse).select_related('product')
    
    for item in stock_items:
        status = 'نفد' if item.quantity == 0 else ('منخفض' if item.is_low_stock else 'طبيعي')
        
        writer.writerow([
            item.product.name,
            item.product.code,
            float(item.quantity),
            float(item.available_quantity),
            float(item.reserved_quantity),
            item.product.get_unit_display(),
            item.location or '',
            float(item.product.cost_price),
            float(item.quantity * item.product.cost_price),
            item.product.min_stock_level,
            status
        ])
    
    return response


@login_required
def export_warehouses_csv(request):
    """تصدير قائمة المخازن إلى CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="warehouses_list.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'اسم المخزن', 'كود المخزن', 'المدير', 'الحالة', 'عدد المنتجات', 
        'القيمة الإجمالية', 'تاريخ الإنشاء', 'آخر تحديث', 'الوصف'
    ])
    
    # Apply same filters as list view
    warehouses = Warehouse.objects.select_related('manager').all()
    search = request.GET.get('search')
    status = request.GET.get('status')
    
    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )
    if status == 'active':
        warehouses = warehouses.filter(is_active=True)
    elif status == 'inactive':
        warehouses = warehouses.filter(is_active=False)
    
    for warehouse in warehouses:
        # Calculate stock info
        stock_items = StockItem.objects.filter(warehouse=warehouse)
        total_products = stock_items.count()
        total_value = sum(item.quantity * item.product.cost_price for item in stock_items)
        
        writer.writerow([
            warehouse.name,
            warehouse.code,
            warehouse.manager.get_full_name() if warehouse.manager else 'غير محدد',
            'نشط' if warehouse.is_active else 'غير نشط',
            total_products,
            float(total_value),
            warehouse.created_at.strftime('%Y-%m-%d'),
            warehouse.updated_at.strftime('%Y-%m-%d') if warehouse.updated_at else '',
            warehouse.description or ''
        ])
    
    return response


class StockItemAPIView(LoginRequiredMixin, View):
    """API للحصول على معلومات عنصر مخزون محدد"""
    
    def get(self, request, stock_id):
        try:
            stock_item = StockItem.objects.select_related('product', 'warehouse').get(id=stock_id)
            
            data = {
                'success': True,
                'id': stock_item.id,
                'product': {
                    'id': stock_item.product.id,
                    'name': stock_item.product.name,
                    'code': stock_item.product.code,
                    'unit': stock_item.product.get_unit_display(),
                },
                'warehouse': {
                    'id': stock_item.warehouse.id,
                    'name': stock_item.warehouse.name,
                    'code': stock_item.warehouse.code,
                },
                'quantity': float(stock_item.quantity),
                'available_quantity': float(stock_item.available_quantity),
                'reserved_quantity': float(stock_item.reserved_quantity),
                'location': stock_item.location,
                'is_low_stock': stock_item.is_low_stock,
                'last_updated': stock_item.updated_at.isoformat() if hasattr(stock_item, 'updated_at') and stock_item.updated_at else None
            }
            
            return JsonResponse(data)
            
        except StockItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'عنصر المخزون غير موجود'}, status=404)


@login_required
@require_http_methods(["POST"])
def quick_stock_adjustment(request):
    """تسوية سريعة للمخزون"""
    try:
        import json
        data = json.loads(request.body)
        
        stock_item_id = data.get('stock_item_id')
        new_quantity = float(data.get('new_quantity', 0))
        reason = data.get('reason', '')
        
        if new_quantity < 0:
            return JsonResponse({'success': False, 'error': 'الكمية لا يمكن أن تكون سالبة'})
        
        stock_item = StockItem.objects.get(id=stock_item_id)
        old_quantity = stock_item.quantity
        difference = new_quantity - old_quantity
        
        # تحديث الكمية
        stock_item.quantity = new_quantity
        stock_item.save()
        
        # إنشاء حركة تسوية
        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='adjustment',
            quantity=difference,
            reference_number=f'QA-{timezone.now().strftime("%Y%m%d%H%M%S")}',
            notes=f'تسوية سريعة: {reason}. الكمية السابقة: {old_quantity}',
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم تحديث الكمية من {old_quantity} إلى {new_quantity}',
            'old_quantity': float(old_quantity),
            'new_quantity': float(new_quantity),
            'difference': float(difference)
        })
        
    except StockItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'عنصر المخزون غير موجود'})
    except ValueError:
        return JsonResponse({'success': False, 'error': 'قيمة غير صحيحة'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})





# Import/Export utilities
from django.http import HttpResponse
import csv
from datetime import datetime, timedelta

@login_required
def import_stock_csv(request):
    """استيراد المخزون من ملف CSV"""
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        try:
            # قراءة الملف
            decoded_file = csv_file.read().decode('utf-8-sig')
            csv_data = csv.DictReader(decoded_file.splitlines())
            
            success_count = 0
            error_count = 0
            errors = []
            
            for row_num, row in enumerate(csv_data, start=2):
                try:
                    warehouse_code = row.get('كود المخزن', '').strip()
                    product_code = row.get('كود المنتج', '').strip()
                    quantity = float(row.get('الكمية', 0))
                    location = row.get('الموقع', '').strip()
                    
                    if not warehouse_code or not product_code:
                        errors.append(f'السطر {row_num}: كود المخزن أو المنتج مفقود')
                        error_count += 1
                        continue
                    
                    warehouse = Warehouse.objects.get(code=warehouse_code)
                    product = Product.objects.get(code=product_code)
                    
                    stock_item, created = StockItem.objects.get_or_create(
                        warehouse=warehouse,
                        product=product,
                        defaults={'quantity': quantity, 'location': location}
                    )
                    
                    if not created:
                        old_quantity = stock_item.quantity
                        stock_item.quantity = quantity
                        stock_item.location = location
                        stock_item.save()
                        
                        # إنشاء حركة تسوية إذا تغيرت الكمية
                        if old_quantity != quantity:
                            StockMovement.objects.create(
                                stock_item=stock_item,
                                movement_type='adjustment',
                                quantity=quantity - old_quantity,
                                reference_number=f'IMPORT-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                                notes=f'استيراد من CSV. الكمية السابقة: {old_quantity}',
                                created_by=request.user
                            )
                    
                    success_count += 1
                    
                except (Warehouse.DoesNotExist, Product.DoesNotExist) as e:
                    errors.append(f'السطر {row_num}: {str(e)}')
                    error_count += 1
                except ValueError as e:
                    errors.append(f'السطر {row_num}: خطأ في البيانات - {str(e)}')
                    error_count += 1
                except Exception as e:
                    errors.append(f'السطر {row_num}: خطأ غير متوقع - {str(e)}')
                    error_count += 1
            
            # رسائل النتائج
            if success_count > 0:
                messages.success(request, f'تم استيراد {success_count} عنصر بنجاح')
            
            if error_count > 0:
                error_message = f'فشل في استيراد {error_count} عنصر:\n' + '\n'.join(errors[:10])
                if len(errors) > 10:
                    error_message += f'\n... و {len(errors) - 10} أخطاء أخرى'
                messages.error(request, error_message)
            
        except Exception as e:
            messages.error(request, f'خطأ في قراءة الملف: {str(e)}')
    
    return redirect('warehouses:stock_list')

# Add these new views to your existing views.py

# Import the new models at the top
from .models import Category, Warehouse, Product, StockItem, StockMovement, StockTransfer, Unit, UnitConversion

# Units Management
class UnitListView(LoginRequiredMixin, ListView):
    model = Unit
    template_name = 'warehouses/unit_list.html'
    context_object_name = 'units'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Unit.objects.all()
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(symbol__icontains=search)
            )
        
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
            
        return queryset.order_by('name')

class UnitCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Unit
    form_class = UnitForm
    template_name = 'warehouses/unit_form.html'
    success_url = reverse_lazy('warehouses:unit_list')
    permission_required = 'warehouses.add_unit'    
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة الوحدة بنجاح!')
        return super().form_valid(form)

class UnitUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = 'warehouses/unit_form.html'
    success_url = reverse_lazy('warehouses:unit_list')
    permission_required = 'warehouses.change_unit'    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الوحدة بنجاح!')
        return super().form_valid(form)

class UnitDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Unit
    template_name = 'warehouses/unit_confirm_delete.html'
    success_url = reverse_lazy('warehouses:unit_list')
    permission_required = 'warehouses.delete_unit'
# Unit Conversions Management
class UnitConversionListView(LoginRequiredMixin, ListView):
    model = UnitConversion
    template_name = 'warehouses/unit_conversion_list.html'
    context_object_name = 'conversions'
    paginate_by = 20
    
    def get_queryset(self):
        return UnitConversion.objects.select_related('from_unit', 'to_unit').order_by('from_unit__name')

class UnitConversionCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = UnitConversion
    form_class = UnitConversionForm
    template_name = 'warehouses/unit_conversion_form.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    permission_required = 'warehouses.add_unitconversion'    
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة تحويل الوحدة بنجاح!')
        return super().form_valid(form)

class UnitConversionUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = UnitConversion
    form_class = UnitConversionForm
    template_name = 'warehouses/unit_conversion_form.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    permission_required = 'warehouses.change_unitconversion'    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث تحويل الوحدة بنجاح!')
        return super().form_valid(form)

class UnitConversionDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = UnitConversion
    template_name = 'warehouses/unit_conversion_confirm_delete.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    permission_required = 'warehouses.delete_unitconversion'
    
# API for unit conversion
class UnitConversionAPIView(LoginRequiredMixin, View):
    def get(self, request):
        from_unit_id = request.GET.get('from_unit')
        to_unit_id = request.GET.get('to_unit')
        quantity = request.GET.get('quantity', 1)
        
        try:
            from_unit = Unit.objects.get(id=from_unit_id)
            to_unit = Unit.objects.get(id=to_unit_id)
            quantity = float(quantity)
            
            converted_quantity = UnitConversion.convert_quantity(quantity, from_unit, to_unit)
            
            return JsonResponse({
                'success': True,
                'converted_quantity': float(converted_quantity),
                'from_unit': from_unit.name,
                'to_unit': to_unit.name,
                'original_quantity': quantity
            })
            
        except (Unit.DoesNotExist, ValueError) as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })



class WarehouseDetailPDFView(LoginRequiredMixin, View):
    """
    Generates a PDF report for a single warehouse's stock.
    """
    def get(self, request, *args, **kwargs):
        warehouse = get_object_or_404(Warehouse, pk=self.kwargs['pk'])
        # Filter out items with zero quantity
        stock_items = StockItem.objects.filter(
            warehouse=warehouse, 
            quantity__gt=0
        ).select_related('product').order_by('product__name')
        
        total_value = sum(item.total_value for item in stock_items)

        context = {
            'warehouse': warehouse,
            'stock_items': stock_items,
            'total_value': total_value,
            'timestamp': timezone.now(),
        }

        # Render the HTML template from the new path to a string
        html_string = render_to_string('pdf/warehouses/warehouse_detail_pdf.html', context)
        
        try:
            # Configure pdfkit to point to the wkhtmltopdf executable
            # IMPORTANT: You may need to change this path depending on your system
            config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
            
            # Generate the PDF from the HTML string
            pdf = pdfkit.from_string(html_string, False, configuration=config, options={"enable-local-file-access": ""})

            # Create an HTTP response with the PDF
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="warehouse_report_{warehouse.code}.pdf"'
            
            return response
            
        except FileNotFoundError:
            # Handle the case where wkhtmltopdf is not found
            messages.error(request, "Could not generate PDF. wkhtmltopdf executable not found.")
            return redirect('warehouses:warehouse_detail', pk=warehouse.pk)
        except Exception as e:
            messages.error(request, f"An unexpected error occurred while generating the PDF: {e}")
            return redirect('warehouses:warehouse_detail', pk=warehouse.pk)


class GenerateProductCodeView(LoginRequiredMixin, View):
    """
    An API endpoint that generates the next available product code for a given product type.
    """
    def get(self, request, *args, **kwargs):
        product_type = request.GET.get('product_type')
        if not product_type:
            return JsonResponse({'error': 'Product type is required.'}, status=400)

        # Define the prefixes for each product type
        prefix_map = {
            'fabric': 'FAB',
            'thread': 'THR',
            'button': 'BTN',
            'zipper': 'ZIP',
            'accessory': 'ACC',
            'finished': 'FIN',
        }
        prefix = prefix_map.get(product_type, 'PROD')
        
        # Find the last product with the same prefix to determine the next number
        last_product = Product.objects.filter(code__startswith=f'{prefix}-').order_by('code').last()
        
        next_num = 1
        if last_product:
            try:
                # Extract the numeric part of the code and increment it
                last_num = int(last_product.code.split('-')[-1])
                next_num = last_num + 1
            except (ValueError, IndexError):
                # Fallback in case the last code has an unexpected format
                next_num = Product.objects.filter(product_type=product_type).count() + 1

        # Loop to ensure the generated code is truly unique, avoiding race conditions
        while True:
            new_code = f"{prefix}-{next_num:04d}" # e.g., FAB-0001
            if not Product.objects.filter(code=new_code).exists():
                break
            next_num += 1
        
        return JsonResponse({'code': new_code})

class ProductDetailPDFView(LoginRequiredMixin, View):
    """
    يقوم بإنشاء تقرير PDF لمنتج واحد.
    """
    def get(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=self.kwargs['pk'])
        stock_items = StockItem.objects.filter(product=product).select_related('warehouse')
        recent_movements = StockMovement.objects.filter(
            stock_item__product=product
        ).select_related('stock_item__warehouse', 'created_by').order_by('-created_at')[:20]

        context = {
            'product': product,
            'stock_items': stock_items,
            'recent_movements': recent_movements,
            'timestamp': timezone.now(),
        }

        # تم تحديث مسار القالب ليتوافق مع هيكل مشروعك
        html_string = render_to_string('pdf/warehouses/product_detail_pdf.html', context)
        
        try:
            # تأكد من أن مسار WKHTMLTOPDF_PATH صحيح في ملف settings.py
            config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
            
            pdf = pdfkit.from_string(html_string, False, configuration=config, options={"enable-local-file-access": ""})

            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="product_report_{product.code}.pdf"'
            
            return response
            
        except FileNotFoundError:
            messages.error(request, "لا يمكن إنشاء ملف PDF. لم يتم العثور على ملف wkhtmltopdf.")
            return redirect('warehouses:product_detail', pk=product.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع أثناء إنشاء ملف PDF: {e}")
            return redirect('warehouses:product_detail', pk=product.pk)
