import logging
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
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
from django.core.paginator import Paginator
from decimal import Decimal, InvalidOperation
from .models import Product, Category
import pandas as pd
import io
import json
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
import csv
from datetime import datetime, timedelta
from .forms import CategoryForm, StockItemUpdateForm, StockTransferForm, WarehouseForm, ProductForm, StockItemForm, UnitForm,UnitConversionForm, StockMovementForm
from django import forms  # <-- Add this import to fix the error
# views.py
from django.core.exceptions import AppRegistryNotReady  # Add this import above

try:
    from production.models import SizeGroup
    PRODUCTION_APP_AVAILABLE = True
except (ImportError, AppRegistryNotReady):
    PRODUCTION_APP_AVAILABLE = False




class WarehouseDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'warehouses/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Eager load related data for efficiency
        all_stock = StockItem.objects.filter(product__is_active=True).select_related('product', 'warehouse')

        # Calculate total stock value in Python to handle potential Decimal/float issues
        total_stock_value = sum(item.total_value for item in all_stock)
        
        # Stock distribution by product type
        stock_by_type = all_stock.values('product__product_type').annotate(
            total_value=Sum(F('quantity') * F('product__cost_price'))
        ).order_by('-total_value')

        product_type_display = dict(Product.PRODUCT_TYPES)
        stock_by_type_data = {
            "labels": [product_type_display.get(item['product__product_type'], 'غير معروف') for item in stock_by_type],
            "values": [float(item['total_value'] or 0) for item in stock_by_type]
        }

        # Top 5 most valuable products (calculated in Python for flexibility)
        top_value_products = sorted(
            [item for item in all_stock if item.total_value > 0], 
            key=lambda x: x.total_value, 
            reverse=True
        )[:5]
        
        for p in top_value_products:
            p.percentage_of_total = (p.total_value / total_stock_value * 100) if total_stock_value > 0 else 0

        # Top 5 warehouses by stock value
        top_warehouses = Warehouse.objects.filter(is_active=True).annotate(
            value=Sum(F('stock_items__quantity') * F('stock_items__product__cost_price'))
        ).filter(value__gt=0).order_by('-value')[:5]

        top_warehouses_data = {
            "labels": [w.name for w in top_warehouses],
            "values": [float(w.value or 0) for w in top_warehouses]
        }

        context.update({
            'total_products': Product.objects.filter(is_active=True).count(),
            'low_stock_items': all_stock.filter(quantity__lte=F('product__min_stock_level'), quantity__gt=0).count(),
            'pending_transfers': StockTransfer.objects.filter(status='pending').count(),
            'recent_movements': StockMovement.objects.select_related('stock_item__product', 'stock_item__warehouse').order_by('-created_at')[:10],
            'total_stock_value': total_stock_value,
            'top_value_products': top_value_products,
            'stock_by_type_json': json.dumps(stock_by_type_data, ensure_ascii=False),
            'top_warehouses_json': json.dumps(top_warehouses_data, ensure_ascii=False),
        })
        return context

# Categories
class CategoryListView(LoginRequiredMixin,ListView):
    model = Category
    template_name = 'warehouses/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20
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

class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'warehouses/category_form.html'
    success_url = reverse_lazy('warehouses:category_list')
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة التصنيف بنجاح!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء المذكورة.')
        return super().form_invalid(form)

class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'warehouses/category_detail.html'
    context_object_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.get_object()

        # Get all related products for pagination
        product_list = category.product_set.all().order_by('name')

        # Set up the paginator
        paginator = Paginator(product_list, 15)  # Show 15 products per page
        page_number = self.request.GET.get('page')
        products_page = paginator.get_page(page_number)

        context['products_page'] = products_page
        context['products_count'] = product_list.count()
        return context
class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'warehouses/category_form.html'
    success_url = reverse_lazy('warehouses:category_list')
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث التصنيف بنجاح!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء المذكورة.')
        return super().form_invalid(form)

class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = 'warehouses/category_confirm_delete.html'
    success_url = reverse_lazy('warehouses:category_list')
    required_roles = ['admin']
class CategorySearchView(LoginRequiredMixin,View):
    def get(self, request):
        search = request.GET.get('q', '')
        categories = Category.objects.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )[:10]
        
        data = [{'id': cat.id, 'name': cat.name} for cat in categories]
        return JsonResponse({'categories': data})

# Products
class ProductListView(LoginRequiredMixin,ListView):
    model = Product
    template_name = 'warehouses/product_list.html'
    context_object_name = 'products'
    paginate_by = 25
    
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass filter choices to the template
        context['categories'] = Category.objects.filter(is_active=True)
        context['product_types'] = Product.PRODUCT_TYPES
        return context
class WarehouseProductStockAPIView(LoginRequiredMixin, View):
    """
    API endpoint to fetch products that have a stock item in a specific warehouse.
    Returns a list of products with their ID, name, and available quantity.
    """
    def get(self, request, warehouse_id):
        try:
            # We only want products that actually exist as StockItems in this warehouse
            # and are active.
            stock_items = StockItem.objects.filter(
                warehouse_id=warehouse_id,
                product__is_active=True
            ).select_related('product').order_by('product__name')

            products_data = []
            for item in stock_items:
                products_data.append({
                    'id': item.product.id,
                    'name': f"{item.product.name} ({item.product.code})",
                    'available_quantity': float(item.available_quantity)
                })

            return JsonResponse({'products': products_data})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class ProductListPDFView(LoginRequiredMixin, View):
    """
    Generates a PDF report for the filtered list of products.
    """
    template_name = 'pdf/warehouses/product_list_pdf.html'

    def get(self, request, *args, **kwargs):
        # Reuse the filtering logic from ProductListView
        product_list_view = ProductListView()
        product_list_view.request = request
        queryset = product_list_view.get_queryset() # This gets the filtered list

        # Prepare context for the PDF template header
        category_id = request.GET.get('category')
        product_type_code = request.GET.get('product_type')
        
        category_name = None
        if category_id:
            try:
                category_name = Category.objects.get(id=category_id).name
            except Category.DoesNotExist:
                pass

        product_type_name = dict(Product.PRODUCT_TYPES).get(product_type_code)

        context = {
            'products': queryset,
            'timestamp': timezone.now(),
            'filters': {
                'search': request.GET.get('search', ''),
                'category_name': category_name,
                'product_type_name': product_type_name,
            }
        }

        html_string = render_to_string(self.template_name, context, request=request)
        
        try:
            # IMPORTANT: Ensure WKHTMLTOPDF_PATH is set in settings.py
            config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
            # Options to enable local file access for CSS and to handle headers/footers
            options = {
                'page-size': 'A4',
                'orientation': 'Landscape',
                'encoding': "UTF-8",
                'enable-local-file-access': True,
                'header-font-size': '8',
                'footer-font-size': '8',
            }
            pdf = pdfkit.from_string(html_string, False, configuration=config, options=options)
            
            response = HttpResponse(pdf, content_type='application/pdf')
            # Use 'inline' to display in browser, 'attachment' to force download
            response['Content-Disposition'] = 'inline; filename="product_list_report.pdf"'
            return response
        except FileNotFoundError:
            messages.error(request, "Could not generate PDF. wkhtmltopdf executable not found. Please check server configuration.")
            return redirect('warehouses:product_list')
        except Exception as e:
            # Log the error for debugging
            print(f"PDF generation error: {e}")
            messages.error(request, f"An unexpected error occurred while generating the PDF: {e}")
            return redirect('warehouses:product_list')


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm # Use the new comprehensive form
    template_name = 'warehouses/product_form.html'
    success_url = reverse_lazy('warehouses:product_list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المنتج بنجاح.")
        return super().form_valid(form)

class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'warehouses/product_detail.html'
    context_object_name = 'product'


    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context['stock_items'] = StockItem.objects.filter(product=product).select_related('warehouse')
        context['recent_movements'] = StockMovement.objects.filter(
            stock_item__product=product
        ).select_related('stock_item__warehouse', 'created_by')[:10]
        return context

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm # Use the new comprehensive form
    template_name = 'warehouses/product_form.html'
    success_url = reverse_lazy('warehouses:product_list')

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث المنتج بنجاح.")
        return super().form_valid(form)

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'warehouses/product_confirm_delete.html'
    success_url = reverse_lazy('warehouses:product_list')

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

class WarehouseListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = 'warehouses/warehouse_list.html'
    context_object_name = 'warehouses'
    paginate_by = 12 # Adjusted for card layout
    
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

class WarehouseCreateView(CreateView ,LoginRequiredMixin):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'warehouses/warehouse_form.html'
    success_url = reverse_lazy('warehouses:warehouse_list')

    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء المخزن بنجاح.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'إنشاء مخزن جديد'
        return context

class WarehouseDetailView(DetailView ,LoginRequiredMixin):
    model = Warehouse
    template_name = 'warehouses/warehouse_detail.html'
    context_object_name = 'warehouse'
    
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

class WarehouseUpdateView(UpdateView ,LoginRequiredMixin):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'warehouses/warehouse_form.html'
    success_url = reverse_lazy('warehouses:warehouse_list')

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث المخزن بنجاح.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'تعديل المخزن'
        return context

# --- FIX: Added the missing WarehouseDeleteView ---
class WarehouseDeleteView(LoginRequiredMixin, DeleteView):
    model = Warehouse
    template_name = 'warehouses/warehouse_confirm_delete.html'
    success_url = reverse_lazy('warehouses:warehouse_list')

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

class StockListView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'warehouses/stock_list.html'
    context_object_name = 'stock_items'
    paginate_by = 25
    
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


class StockCreateView(LoginRequiredMixin, View):
    """
    Handles the creation of new stock items. If a stock item for the selected
    product and warehouse already exists, it adds the specified quantity to it.
    This view is now protected against double-submission errors.
    """
    template_name = 'warehouses/stock_form.html'

    def get_form(self):
        """Defines the form used for creating stock."""
        class StockForm(forms.Form):
            warehouse = forms.ModelChoiceField(
                queryset=Warehouse.objects.filter(is_active=True),
                label="المخزن",
                empty_label="اختر المخزن",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            product = forms.ModelChoiceField(
                queryset=Product.objects.filter(is_active=True),
                label="المنتج",
                empty_label="اختر المنتج",
                widget=forms.Select(attrs={'class': 'form-select'})
            )
            quantity = forms.DecimalField(
                label="الكمية",
                min_value=0.01,
                decimal_places=2,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
            )
            location = forms.CharField(
                label="الموقع في المخزن (اختياري)",
                required=False,
                max_length=100,
                widget=forms.TextInput(attrs={'class': 'form-control'})
            )
        return StockForm

    def get(self, request, *args, **kwargs):
        """Handles GET requests by displaying the empty stock creation form."""
        StockForm = self.get_form()
        form = StockForm()
        return render(request, self.template_name, {'form': form})

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Handles POST requests to create or update stock.
        Includes a check to prevent duplicate submissions from adding double quantity.
        """
        logger = logging.getLogger(__name__)
        StockForm = self.get_form()
        form = StockForm(request.POST)

        if form.is_valid():
            warehouse = form.cleaned_data['warehouse']
            product = form.cleaned_data['product']
            quantity = form.cleaned_data['quantity']
            location = form.cleaned_data.get('location', '')

            logger.info(f"Stock creation request from user {request.user.username} for {quantity} of '{product.name}' in '{warehouse.name}'")

            # --- FIX: IDEMPOTENCY CHECK TO PREVENT DOUBLE SUBMISSION ---
            # This check prevents the same operation from running twice if a user double-clicks the submit button.
            ten_seconds_ago = timezone.now() - timedelta(seconds=10)
            if StockMovement.objects.filter(
                stock_item__warehouse=warehouse,
                stock_item__product=product,
                movement_type='in',
                quantity=quantity,
                created_by=request.user,
                created_at__gte=ten_seconds_ago
            ).exists():
                messages.warning(request, 'تم استلام هذا الطلب بالفعل. ربما قمت بالنقر على زر الإضافة مرتين؟')
                return redirect('warehouses:stock_list')

            try:
                # Use get_or_create to atomically find or create the stock item.
                # The 'defaults' are only used if a new item is being created.
                stock_item, created = StockItem.objects.get_or_create(
                    warehouse=warehouse,
                    product=product,
                    defaults={'quantity': 0, 'location': location}
                )

                # Determine notes and log message based on whether the item was created or found.
                if created:
                    logger.info("Created a new stock item.")
                    movement_notes = 'إنشاء مخزون جديد'
                else:
                    logger.info(f"Found existing stock item. Current quantity: {stock_item.quantity}")
                    movement_notes = f'إضافة مخزون. الكمية السابقة: {stock_item.quantity}'
                    # If a new location is provided for an existing item, update it.
                    if location:
                        stock_item.location = location
                        stock_item.save(update_fields=['location'])

                # Create a stock movement record. The post_save signal on StockMovement
                # will handle the actual quantity update on the StockItem.
                StockMovement.objects.create(
                    stock_item=stock_item,
                    movement_type='in',
                    quantity=quantity,
                    reference_number=f'ADD-{timezone.now().strftime("%Y%m%d%H%M%S")}',
                    notes=movement_notes,
                    created_by=request.user
                )

                # Refresh the instance from the database to get the updated quantity from the signal.
                stock_item.refresh_from_db()

                # Provide clear feedback to the user.
                if created:
                    messages.success(request, f'تم إنشاء عنصر مخزون جديد للمنتج "{product.name}" بكمية {stock_item.quantity}.')
                else:
                    messages.success(request, f'تم إضافة {quantity} للمنتج "{product.name}". الكمية الإجمالية الآن: {stock_item.quantity}.')

                return redirect('warehouses:stock_list')

            except Exception as e:
                logger.error(f"An unexpected error occurred during stock creation: {str(e)}")
                messages.error(request, f'حدث خطأ غير متوقع أثناء معالجة طلبك: {str(e)}')
                return render(request, self.template_name, {'form': form})

        else:
            messages.error(request, 'يرجى تصحيح الأخطاء الموجودة في النموذج.')
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


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_movements'] = self.object.movements.all()[:10]
        return context


class InventoryCountView(LoginRequiredMixin, TemplateView):
    """
    A professional view for performing a full inventory count (جرد المخزون).
    """
    template_name = 'warehouses/inventory_count.html'

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

class StockUpdateView(LoginRequiredMixin, UpdateView):
    model = StockItem
    # Use the new, specific update form
    form_class = StockItemUpdateForm
    template_name = 'warehouses/stock_form.html'
    success_url = reverse_lazy('warehouses:stock_list')

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
        queryset = StockMovement.objects.select_related(
            'stock_item__product', 'stock_item__warehouse', 'created_by'
        ).order_by('-created_at')

        # --- Filtering & Searching Logic ---
        
        # General Search
        search_query = self.request.GET.get('q', '')
        if search_query:
            queryset = queryset.filter(
                Q(stock_item__product__name__icontains=search_query) |
                Q(stock_item__product__code__icontains=search_query) |
                Q(reference_number__icontains=search_query) |
                Q(notes__icontains=search_query)
            )

        # Specific Filters
        warehouse_filter = self.request.GET.get('warehouse')
        if warehouse_filter:
            queryset = queryset.filter(stock_item__warehouse_id=warehouse_filter)

        movement_type_filter = self.request.GET.get('movement_type')
        if movement_type_filter:
            queryset = queryset.filter(movement_type=movement_type_filter)

        date_from_filter = self.request.GET.get('date_from')
        if date_from_filter:
            queryset = queryset.filter(created_at__date__gte=date_from_filter)
        
        date_to_filter = self.request.GET.get('date_to')
        if date_to_filter:
            queryset = queryset.filter(created_at__date__lte=date_to_filter)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        
        # Pass all query parameters to the template for pagination
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['query_params'] = query_params.urlencode()
        
        # Pass filter values back to the template to keep them in the form
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'warehouse': self.request.GET.get('warehouse', ''),
            'movement_type': self.request.GET.get('movement_type', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context


@login_required
def print_stock_movements_pdf(request):
    """
    Generates a PDF report of stock movements based on the provided filters.
    """
    movements = StockMovement.objects.select_related(
        'stock_item__product', 'stock_item__warehouse', 'created_by'
    ).order_by('-created_at')

    filters_applied = {}

    # --- START: FIX for AttributeError ---
    # The StockMovement model does not have a MOVEMENT_CHOICES attribute.
    # We define the mapping here based on the values in the template.
    movement_type_display_names = {
        'in': 'وارد',
        'out': 'صادر',
        'transfer': 'تحويل',
        'adjustment': 'تسوية',
        'return': 'مرتجع',
    }
    # --- END: FIX ---

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        try:
            movements = movements.filter(stock_item__warehouse_id=warehouse_id)
            filters_applied['warehouse'] = Warehouse.objects.get(pk=warehouse_id).name
        except Warehouse.DoesNotExist:
            pass # Or handle error appropriately

    movement_type = request.GET.get('movement_type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
        # Use the locally defined dictionary for the lookup
        filters_applied['movement_type'] = movement_type_display_names.get(movement_type)
    
    date_from = request.GET.get('date_from')
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
        filters_applied['date_from'] = date_from

    date_to = request.GET.get('date_to')
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
        filters_applied['date_to'] = date_to

    # Prepare context for the PDF template
    context = {
        'movements': movements,
        'filters': filters_applied,
        'timestamp': timezone.now(),
        'user': request.user.get_full_name() or request.user.username,
    }

    # Render the PDF template to an HTML string
    html_string = render_to_string('pdf/warehouses/movement_report_pdf.html', context)
    
    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8",
            'page-size': 'A4',
            'orientation': 'Landscape',
            'margin-top': '0.5in',
            'margin-right': '0.5in',
            'margin-bottom': '0.5in',
            'margin-left': '0.5in',
        })
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Stock_Movements_{timezone.now().strftime('%Y-%m-%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {e}<br>Please ensure wkhtmltopdf is installed and configured correctly in settings.py.", status=500)
    
class StockMovementCreateView(LoginRequiredMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = 'warehouses/movement_form.html'
    success_url = reverse_lazy('warehouses:movement_list')

    def get_initial(self):
        """
        If a product_id is passed in the URL, this pre-fills the
        product search field.
        """
        initial = super().get_initial()
        product_id = self.request.GET.get('product_id')
        if product_id:
            try:
                product = Product.objects.get(pk=product_id)
                initial['product'] = product.pk
                initial['product_search'] = f"{product.name} ({product.code})"
            except Product.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        warehouse = form.cleaned_data['warehouse']
        product = form.cleaned_data['product']
        
        # This logic is key: it finds an existing stock item or creates a new one.
        # This is exactly what's needed to add a product to a warehouse for the first time.
        stock_item, created = StockItem.objects.get_or_create(
            warehouse=warehouse,
            product=product,
            defaults={'quantity': 0}
        )
        
        # Prevent creating an 'out' movement for a newly created (and thus empty) stock item.
        if created and form.cleaned_data['movement_type'] == 'out':
            messages.error(self.request, 'لا يمكن عمل حركة "صادر" لمنتج ليس له رصيد في هذا المخزن.')
            stock_item.delete() # Clean up the empty item that was created
            return self.form_invalid(form)

        # Associate the found/created stock_item with the movement instance.
        form.instance.stock_item = stock_item
        form.instance.created_by = self.request.user
        
        messages.success(self.request, 'تم إنشاء حركة المخزون بنجاح.')
        return super().form_valid(form)



class StockMovementDetailView(LoginRequiredMixin, DetailView):
    model = StockMovement
    template_name = 'warehouses/movement_detail.html'
    context_object_name = 'movement'



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


# In your StockTransferCreateView
class StockTransferCreateView(LoginRequiredMixin, CreateView):
    model = StockTransfer
    # --- FIX: Use the form_class we just updated ---
    form_class = StockTransferForm
    template_name = 'warehouses/transfer_form.html'
    success_url = reverse_lazy('warehouses:transfer_list')

    def form_valid(self, form):
        # The validation logic is now in the form, so form_valid is much cleaner.
        form.instance.requested_by = self.request.user

        today = timezone.now().date()
        prefix = f"TR{today.strftime('%Y%m%d')}"
        last_transfer = StockTransfer.objects.filter(transfer_number__startswith=prefix).order_by('-transfer_number').first()

        if last_transfer:
            last_number = int(last_transfer.transfer_number[-4:])
            new_number = last_number + 1
        else:
            new_number = 1

        form.instance.transfer_number = f"{prefix}{new_number:04d}"

        messages.success(self.request, 'تم إنشاء طلب التحويل بنجاح')
        return super().form_valid(form)
class StockTransferDetailView(LoginRequiredMixin, DetailView):
    model = StockTransfer
    template_name = 'warehouses/transfer_detail.html'
    context_object_name = 'transfer'


class StockTransferApproveView(LoginRequiredMixin, View):
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


class StockTransferCompleteView(LoginRequiredMixin, View):
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
class StockAdjustmentView(LoginRequiredMixin, TemplateView):
    """
    A view for performing stock adjustments for a selected warehouse.
    Handles both displaying the stock items and processing the adjustments.
    """
    template_name = 'warehouses/stock_adjustment.html'

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

class UnitCreateView(LoginRequiredMixin, CreateView):
    model = Unit
    form_class = UnitForm
    template_name = 'warehouses/unit_form.html'
    success_url = reverse_lazy('warehouses:unit_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة الوحدة بنجاح!')
        return super().form_valid(form)

class UnitUpdateView(LoginRequiredMixin, UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = 'warehouses/unit_form.html'
    success_url = reverse_lazy('warehouses:unit_list')
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الوحدة بنجاح!')
        return super().form_valid(form)

class UnitDeleteView(LoginRequiredMixin, DeleteView):
    model = Unit
    template_name = 'warehouses/unit_confirm_delete.html'
    success_url = reverse_lazy('warehouses:unit_list')
# Unit Conversions Management
class UnitConversionListView(LoginRequiredMixin, ListView):
    model = UnitConversion
    template_name = 'warehouses/unit_conversion_list.html'
    context_object_name = 'conversions'
    paginate_by = 20
    
    def get_queryset(self):
        return UnitConversion.objects.select_related('from_unit', 'to_unit').order_by('from_unit__name')

class UnitConversionCreateView(LoginRequiredMixin, CreateView):
    model = UnitConversion
    form_class = UnitConversionForm
    template_name = 'warehouses/unit_conversion_form.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    def form_valid(self, form):
        messages.success(self.request, 'تم إضافة تحويل الوحدة بنجاح!')
        return super().form_valid(form)

class UnitConversionUpdateView(LoginRequiredMixin, UpdateView):
    model = UnitConversion
    form_class = UnitConversionForm
    template_name = 'warehouses/unit_conversion_form.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث تحويل الوحدة بنجاح!')
        return super().form_valid(form)

class UnitConversionDeleteView(LoginRequiredMixin, DeleteView):
    model = UnitConversion
    template_name = 'warehouses/unit_conversion_confirm_delete.html'
    success_url = reverse_lazy('warehouses:unit_conversion_list')
    
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

class ProductImportView(LoginRequiredMixin, TemplateView):
    """
    Handles rendering the product import page and processing the uploaded Excel file.
    This view now supports both creating new products and updating existing ones.
    """
    template_name = 'warehouses/product_import.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'استيراد وتحديث المنتجات من Excel'
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Handles the POST request with the uploaded Excel file.
        It validates the file, and for each row, it either updates an
        existing product or creates a new one.
        """
        if 'excel_file' not in request.FILES:
            messages.error(request, 'لم يتم رفع أي ملف.')
            return redirect('warehouses:product_import')

        excel_file = request.FILES['excel_file']
        
        if not excel_file.name.endswith(('.xls', '.xlsx')):
            messages.error(request, 'ملف غير صالح. يرجى رفع ملف Excel بصيغة .xls أو .xlsx.')
            return redirect('warehouses:product_import')

        try:
            df = pd.read_excel(excel_file, dtype=str).fillna('')
            df.columns = df.columns.str.strip()

            required_columns = ['اسم المنتج', 'نوع المنتج']
            if not all(col in df.columns for col in required_columns):
                messages.error(request, f'الملف يفتقد لأحد الأعمدة المطلوبة: {", ".join(required_columns)}')
                return redirect('warehouses:product_import')

            errors = []
            created_count = 0
            updated_count = 0
            
            product_type_map = {v: k for k, v in Product.PRODUCT_TYPES}
            unit_map = {v: k for k, v in Product.UNIT_CHOICES}
            quality_grade_map = {v: k for k, v in Product._meta.get_field('quality_grade').choices}

            for index, row in df.iterrows():
                row_num = index + 2
                
                try:
                    name = str(row.get('اسم المنتج', '')).strip()
                    if not name:
                        errors.append(f'صف {row_num}: اسم المنتج فارغ.')
                        continue
                    
                    def get_choice_key(value, choices_map, choices_tuple):
                        val_str = str(value).strip()
                        if val_str in [c[0] for c in choices_tuple]: return val_str
                        return choices_map.get(val_str)

                    product_type_key = get_choice_key(row.get('نوع المنتج', ''), product_type_map, Product.PRODUCT_TYPES)
                    if not product_type_key:
                        errors.append(f'صف {row_num}: نوع المنتج "{row.get("نوع المنتج", "")}" غير صالح.')
                        continue

                    unit_key = get_choice_key(row.get('الوحدة', ''), unit_map, Product.UNIT_CHOICES)
                    if not unit_key:
                        errors.append(f'صف {row_num}: الوحدة "{row.get("الوحدة", "")}" غير صالحة.')
                        continue

                    category_name = str(row.get('الفئة', '')).strip()
                    category = None
                    if category_name:
                        category, _ = Category.objects.get_or_create(name=category_name)

                    cost_price = Decimal(row.get('سعر التكلفة', 0) or 0)
                    min_stock_level = int(row.get('الحد الأدنى للمخزون', 0) or 0)
                    
                    # This dictionary will hold the data for creation or update.
                    product_defaults = {
                        'name': name,
                        'category': category,
                        'product_type': product_type_key,
                        'cost_price': cost_price,
                        'min_stock_level': min_stock_level,
                        'unit': unit_key,
                    }

                    if product_type_key == 'fabric':
                        width = row.get('العرض (سم)')
                        if not width:
                            errors.append(f'صف {row_num}: حقل "العرض (سم)" مطلوب للقماش.')
                            continue
                        
                        quality_grade_key = get_choice_key(row.get('درجة الجودة', ''), quality_grade_map, Product._meta.get_field('quality_grade').choices)
                        if not quality_grade_key:
                            errors.append(f'صف {row_num}: "درجة الجودة" ({row.get("درجة الجودة", "")}) غير صالحة للقماش.')
                            continue
                        product_defaults.update({'width': Decimal(width), 'quality_grade': quality_grade_key})

                    elif product_type_key == 'finished':
                        selling_price = row.get('سعر البيع')
                        if not selling_price:
                            errors.append(f'صف {row_num}: "سعر البيع" مطلوب للمنتجات النهائية.')
                            continue
                        product_defaults.update({
                            'selling_price': Decimal(selling_price),
                            'colors': str(row.get('الألوان المتاحة', '')).strip(),
                            'fabric_quantity_per_piece': Decimal(row.get('كمية القماش للقطعة', 0) or 0)
                        })

                        if PRODUCTION_APP_AVAILABLE:
                            size_group_name = str(row.get('اسم مجموعة المقاسات', '')).strip()
                            if size_group_name:
                                size_group, created_sg = SizeGroup.objects.get_or_create(name=size_group_name)
                                if created_sg:
                                    sizes_list = [str(row.get(f'مقاس {i}', '')).strip() for i in range(1, 13) if str(row.get(f'مقاس {i}', '')).strip()]
                                    if sizes_list:
                                        size_group.sizes = sizes_list
                                        size_group.save()
                                product_defaults['size_group'] = size_group
                    
                    code = str(row.get('كود المنتج', '')).strip()
                    if code:
                        product_defaults['code'] = code
                    
                    # --- CORE LOGIC CHANGE: UPDATE OR CREATE ---
                    # We use 'name' as the unique identifier to find existing products.
                    # 'defaults' contains all the data to be set on creation or update.
                    product, created = Product.objects.update_or_create(
                        name__iexact=name,
                        defaults=product_defaults
                    )

                    # If the product was just created and no code was provided, generate one.
                    if created and not code:
                         prefix_map = {'fabric': 'FAB', 'finished': 'FIN', 'accessory': 'ACC', 'thread': 'THR', 'button': 'BTN', 'zipper': 'ZIP'}
                         prefix = prefix_map.get(product_type_key, 'PROD')
                         last_product = Product.objects.filter(code__startswith=f'{prefix}-').order_by('code').last()
                         next_num = 1
                         if last_product:
                             try:
                                 last_num = int(last_product.code.split('-')[-1])
                                 next_num = last_num + 1
                             except (ValueError, IndexError): pass
                         while True:
                             new_code = f"{prefix}-{next_num:04d}"
                             if not Product.objects.filter(code=new_code).exists():
                                 product.code = new_code
                                 break
                             next_num += 1
                         product.save()

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    errors.append(f'صف {row_num}: خطأ غير متوقع - {e}')

            if errors:
                transaction.set_rollback(True)
                messages.error(request, 'حدثت أخطاء أثناء الاستيراد. لم يتم حفظ أي منتجات.')
                context = self.get_context_data(errors=errors)
                return self.render_to_response(context)

            # --- UPDATED SUCCESS MESSAGE ---
            success_message = f"اكتملت المعالجة بنجاح. "
            if created_count > 0:
                success_message += f"تم إنشاء {created_count} منتج جديد. "
            if updated_count > 0:
                success_message += f"تم تحديث {updated_count} منتج موجود."
            
            messages.success(request, success_message)
            return redirect('warehouses:product_list')

        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء قراءة الملف: {e}')
            return redirect('warehouses:product_import')

@login_required
def download_product_import_template(request, template_type):
    """
    Generates and serves a specific Excel file template for importing products
    based on the requested type (fabric, finished, other).
    """
    base_columns = [
        'اسم المنتج', 'كود المنتج', 'الفئة', 'نوع المنتج', 
        'سعر التكلفة', 'الحد الأدنى للمخزون', 'الوحدة',
    ]
    
    base_instructions = {
        'اسم المنتج': 'مطلوب. سيتم استخدامه للتحديث إذا كان المنتج موجودًا.',
        'كود المنتج': 'اختياري. سيتم إنشاؤه تلقائيًا للمنتجات الجديدة إذا ترك فارغًا.',
        'الفئة': 'اختياري. سيتم إنشاء فئة جديدة إذا لم تكن موجودة.',
        'الوحدة': f"مطلوب. القيم الصالحة: {', '.join([c[1] for c in Product.UNIT_CHOICES])}", # Show Arabic values
        'سعر التكلفة': 'مطلوب. أدخل 0 إذا لم يكن هناك تكلفة.',
        'الحد الأدنى للمخزون': 'اختياري. القيمة الافتراضية هي 0.',
    }

    if template_type == 'fabric':
        columns = base_columns + ['العرض (سم)', 'درجة الجودة']
        instructions = base_instructions.copy()
        instructions.update({
            'نوع المنتج': "القيمة الثابتة لهذا القالب هي 'قماش'.",
            'العرض (سم)': "مطلوب للقماش.",
            'درجة الجودة': f"مطلوب للقماش. القيم الصالحة: {', '.join([c[1] for c in Product._meta.get_field('quality_grade').choices if c[0]])}", # Show Arabic
        })
        example_row = {'نوع المنتج': 'قماش', 'الوحدة': 'متر'}

    elif template_type == 'finished':
        columns = base_columns + [
            'سعر البيع', 'الألوان المتاحة', 'كمية القماش للقطعة', 
            'اسم مجموعة المقاسات'
        ] + [f'مقاس {i}' for i in range(1, 13)]
        instructions = base_instructions.copy()
        instructions.update({
            'نوع المنتج': "القيمة الثابتة لهذا القالب هي 'منتج نهائي'.",
            'سعر البيع': "مطلوب للمنتج النهائي.",
            'الألوان المتاحة': 'اختياري. مثال: أزرق, أحمر, أخضر',
            'كمية القماش للقطعة': 'اختياري. مثال: 1.25',
            'اسم مجموعة المقاسات': "اختياري. إذا كانت المجموعة غير موجودة، سيتم إنشاؤها مع المقاسات من أعمدة 'مقاس 1' إلى 'مقاس 12'.",
        })
        example_row = {'نوع المنتج': 'منتج نهائي', 'الوحدة': 'قطعة'}

    elif template_type == 'other':
        columns = base_columns
        instructions = base_instructions.copy()
        other_types = [c[1] for c in Product.PRODUCT_TYPES if c[0] not in ['fabric', 'finished']] # Show Arabic
        instructions.update({
            'نوع المنتج': f"مطلوب. اختر من: {', '.join(other_types)}",
        })
        example_row = {}

    else:
        raise Http404("نوع القالب المحدد غير موجود.")

    df = pd.DataFrame([instructions], columns=columns)
    
    for col in columns:
        if col not in example_row:
            example_row[col] = ''
    
    example_df = pd.DataFrame([example_row], columns=columns)
    df = pd.concat([df, example_df], ignore_index=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Products')
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="template_{template_type}.xlsx"'
    
    return response

