from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum, Avg, Count, F
from django.db import models, transaction
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.encoding import smart_str
from django.forms import inlineformset_factory
from decimal import Decimal
from datetime import datetime, timedelta
import csv
from decimal import Decimal
import decimal
# Models
from warehouses.models import Product, Warehouse, StockItem, StockMovement  
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, Payment, 
    SupplierRating, SupplierContact, SupplierDocument,
    PurchaseOrderDelivery, SupplierPerformanceMetric
)

# Forms
from .forms import (
    SupplierForm, PurchaseOrderForm, PaymentForm, 
    SupplierRatingForm
)

PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder, 
    PurchaseOrderItem, 
    fields=['product', 'quantity_ordered', 'unit_price'], 
    extra=1, 
    can_delete=True
)

class SupplierListView(LoginRequiredMixin, ListView):
    """عرض قائمة الموردين"""
    model = Supplier
    template_name = 'suppliers/supplier_list.html'
    context_object_name = 'suppliers'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        
        # البحث
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(contact_person__icontains=search)
            )
        
        # فلترة حسب النوع
        supplier_type = self.request.GET.get('type')
        if supplier_type:
            queryset = queryset.filter(supplier_type=supplier_type)
        
        # فلترة حسب الحالة
        is_active = self.request.GET.get('active')
        if is_active:
            queryset = queryset.filter(is_active=is_active == 'true')
        
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplier_types'] = Supplier.SUPPLIER_TYPES
        context['search'] = self.request.GET.get('search', '')
        context['selected_type'] = self.request.GET.get('type', '')
        context['selected_active'] = self.request.GET.get('active', '')
        return context


class SupplierDetailView(LoginRequiredMixin, DetailView):
    """عرض تفاصيل المورد"""
    model = Supplier
    template_name = 'suppliers/supplier_detail.html'
    context_object_name = 'supplier'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = self.get_object()
        
        # أوامر الشراء الحديثة
        context['recent_orders'] = supplier.purchase_orders.all()[:10]
        
        # الدفعات الحديثة
        context['recent_payments'] = supplier.payments.all()[:10]
        
        # التقييمات
        context['ratings'] = supplier.ratings.all()[:5]
        
        # جهات الاتصال
        context['contacts'] = supplier.contacts.all()
        
        # المستندات
        context['documents'] = supplier.documents.all()
        
        # إحصائيات
        context['stats'] = {
            'total_orders': supplier.purchase_orders.count(),
            'completed_orders': supplier.purchase_orders.filter(status='completed').count(),
            'pending_orders': supplier.purchase_orders.filter(status__in=['pending', 'approved', 'in_delivery']).count(),
            'total_amount': supplier.total_purchases,
            'pending_amount': supplier.pending_amount,
            'average_rating': supplier.ratings.aggregate(avg=Avg('overall_rating'))['avg'] or 0,
        }
        
        return context


class SupplierCreateView(LoginRequiredMixin, CreateView):
    """إنشاء مورد جديد"""
    model = Supplier
    form_class = SupplierForm  # Use form_class instead of fields
    template_name = 'suppliers/supplier_form.html'
    success_url = reverse_lazy('suppliers:list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'تم إنشاء المورد بنجاح')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء أدناه')
        return super().form_invalid(form)
 
class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل المورد"""
    model = Supplier
    form_class = SupplierForm  # Use form_class instead of fields
    template_name = 'suppliers/supplier_form.html'
    
    def get_success_url(self):
        return reverse_lazy('suppliers:detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث بيانات المورد بنجاح')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء أدناه')
        return super().form_invalid(form)
    
class PurchaseOrderListView(LoginRequiredMixin, ListView):
    """عرض قائمة أوامر الشراء"""
    model = PurchaseOrder
    template_name = 'suppliers/purchase_order_list.html'
    context_object_name = 'orders'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related('supplier', 'created_by')
        
        # البحث
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(po_number__icontains=search) |
                Q(supplier__name__icontains=search)
            )
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # فلترة حسب المورد
        supplier_id = self.request.GET.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        # فلترة حسب التاريخ
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(order_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(order_date__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = PurchaseOrder.STATUS_CHOICES
        context['suppliers'] = Supplier.objects.filter(is_active=True)
        context['filters'] = {
            'search': self.request.GET.get('search', ''),
            'status': self.request.GET.get('status', ''),
            'supplier': self.request.GET.get('supplier', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context


class PurchaseOrderDetailView(LoginRequiredMixin, DetailView):
    """عرض تفاصيل أمر الشراء"""
    model = PurchaseOrder
    template_name = 'suppliers/purchase_order_detail.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_object()
        
        # عناصر الأمر
        context['items'] = order.items.select_related('product')
        
        # الدفعات
        context['payments'] = order.payments.all()
        
        # التسليمات
        context['deliveries'] = order.deliveries.all()
        
        # التقييمات
        context['ratings'] = order.ratings.all()
        
        return context


class PaymentListView(LoginRequiredMixin, ListView):
    """عرض قائمة الدفعات"""
    model = Payment
    template_name = 'suppliers/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Payment.objects.select_related('supplier', 'purchase_order', 'created_by')
        
        # فلترة حسب المورد
        supplier_id = self.request.GET.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        # فلترة حسب الحالة
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # فلترة حسب نوع الدفعة
        payment_type = self.request.GET.get('type')
        if payment_type:
            queryset = queryset.filter(payment_type=payment_type)
        
        return queryset.order_by('-payment_date')


class SupplierPerformanceView(LoginRequiredMixin, ListView):
    """عرض أداء الموردين"""
    model = SupplierPerformanceMetric
    template_name = 'suppliers/supplier_performance.html'
    context_object_name = 'metrics'
    
    def get_queryset(self):
        # الحصول على آخر مقاييس الأداء لكل مورد
        return SupplierPerformanceMetric.objects.select_related('supplier').order_by(
            'supplier', '-period_end'
        ).distinct('supplier')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # إحصائيات عامة
        context['total_suppliers'] = Supplier.objects.filter(is_active=True).count()
        context['top_suppliers'] = Supplier.objects.filter(
            is_active=True,
            current_rating__gt=0
        ).order_by('-current_rating')[:5]
        
        return context


# Dashboard Views
class SupplierDashboardView(LoginRequiredMixin, ListView):
    """لوحة تحكم الموردين"""
    model = Supplier
    template_name = 'suppliers/dashboard.html'
    context_object_name = 'suppliers'
    
    def get_queryset(self):
        return Supplier.objects.filter(is_active=True)[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # إحصائيات عامة
        context['stats'] = {
            'total_suppliers': Supplier.objects.filter(is_active=True).count(),
            'total_orders': PurchaseOrder.objects.count(),
            'pending_orders': PurchaseOrder.objects.filter(
                status__in=['pending', 'approved', 'in_delivery']
            ).count(),
            'overdue_orders': PurchaseOrder.objects.filter(
                expected_delivery_date__lt=timezone.now().date(),
                status__in=['pending', 'approved', 'in_delivery']
            ).count(),
        }
        
        # أوامر الشراء الحديثة
        context['recent_orders'] = PurchaseOrder.objects.select_related(
            'supplier'
        ).order_by('-created_at')[:10]
        
        # الدفعات المعلقة
        context['pending_payments'] = Payment.objects.filter(
            status='pending'
        ).select_related('supplier')[:10]
        
        # الموردين الأعلى تقييماً
        context['top_rated_suppliers'] = Supplier.objects.filter(
            is_active=True,
            current_rating__gt=0
        ).order_by('-current_rating')[:5]
        
        # الأوامر المتأخرة
        context['overdue_orders'] = PurchaseOrder.objects.filter(
            expected_delivery_date__lt=timezone.now().date(),
            status__in=['pending', 'approved', 'in_delivery']
        ).select_related('supplier')[:10]
        
        return context

# Add these new views to your existing views.py file

class PurchaseOrderCreateView(LoginRequiredMixin, CreateView):
    """إنشاء أمر شراء جديد"""
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'suppliers/purchase_order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST)
        else:
            context['formset'] = PurchaseOrderItemFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.po_number = generate_po_number()
            self.object = form.save()
            
            if formset.is_valid():
                formset.instance = self.object
                formset.save()
                
                # حساب المبالغ
                self.object.calculate_totals()
                
                messages.success(self.request, 'تم إنشاء أمر الشراء بنجاح')
                return redirect(self.get_success_url())
            else:
                return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('suppliers:purchase_order_detail', kwargs={'pk': self.object.pk})
    
class PurchaseOrderUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل أمر الشراء"""
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'suppliers/purchase_order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = PurchaseOrderItemFormSet(instance=self.object)
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        with transaction.atomic():
            self.object = form.save()
            
            if formset.is_valid():
                formset.save()
                
                # حساب المبالغ
                self.object.calculate_totals()
                
                messages.success(self.request, 'تم تحديث أمر الشراء بنجاح')
                return redirect(self.get_success_url())
            else:
                return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('suppliers:purchase_order_detail', kwargs={'pk': self.object.pk})

    

# Replace the purchase_order_receive function (around line 400)
def purchase_order_receive(request, pk):
    """استلام أمر الشراء"""
    purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if purchase_order.status not in ['approved', 'in_delivery']:
        messages.error(request, 'لا يمكن استلام هذا الأمر في الحالة الحالية')
        return redirect('suppliers:purchase_order_detail', pk=pk)
    
    # Get items that still need to be received
    items = purchase_order.items.filter(
        quantity_received__lt=models.F('quantity_ordered')
    ).select_related('product')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                warehouse_id = request.POST.get('warehouse')
                received_date = request.POST.get('received_date')
                delivery_notes = request.POST.get('delivery_notes', '')
                
                if not warehouse_id or not received_date:
                    return JsonResponse({
                        'success': False,
                        'error': 'يرجى ملء جميع الحقول المطلوبة'
                    })
                
                # Get warehouse
                try:
                    from warehouses.models import Warehouse
                    warehouse = Warehouse.objects.get(id=warehouse_id)
                except Warehouse.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'المخزن المحدد غير موجود'
                    })
                
                # Parse received date
                try:
                    from datetime import datetime
                    received_date = datetime.strptime(received_date, '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'error': 'تاريخ غير صحيح'
                    })
                
                # Create delivery record
                delivery = PurchaseOrderDelivery.objects.create(
                    purchase_order=purchase_order,
                    delivery_number=generate_delivery_number(),
                    delivery_date=received_date,
                    received_by=request.user,
                    warehouse=warehouse,
                    delivery_notes=delivery_notes,
                    quality_check_passed=True
                )
                
                # Process items
                items_received = 0
                all_received = True
                
                for item in items:
                    quantity_key = f'item_{item.id}_quantity'
                    notes_key = f'item_{item.id}_notes'
                    
                    received_quantity_str = request.POST.get(quantity_key, '0')
                    item_notes = request.POST.get(notes_key, '')
                    
                    # Handle different decimal separators and convert to Decimal
                    try:
                        # Clean the string and convert to Decimal
                        cleaned_quantity = received_quantity_str.replace(',', '.').strip()
                        received_quantity = Decimal(cleaned_quantity) if cleaned_quantity else Decimal('0')
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        received_quantity = Decimal('0')
                    
                    if received_quantity > 0:
                        # Validate quantity - convert to Decimal for comparison
                        max_quantity = item.quantity_ordered - item.quantity_received
                        if received_quantity > max_quantity:
                            return JsonResponse({
                                'success': False,
                                'error': f'الكمية المدخلة للمنتج {item.product.name} تتجاوز الحد المسموح ({max_quantity})'
                            })
                        
                        # Update item received quantity
                        item.quantity_received += received_quantity
                        item.save()
                        
                        # Add to warehouse stock
                        from warehouses.models import StockItem, StockMovement
                        stock_item, created = StockItem.objects.get_or_create(
                            warehouse=warehouse,
                            product=item.product,
                            defaults={'quantity': Decimal('0')}
                        )
                        stock_item.quantity += received_quantity
                        stock_item.save()
                        
                        # Record stock movement
                        StockMovement.objects.create(
                            stock_item=stock_item,
                            movement_type='in',
                            quantity=received_quantity,
                            reference_number=purchase_order.po_number,
                            notes=f'استلام من أمر الشراء {purchase_order.po_number}' + 
                                  (f' - {item_notes}' if item_notes else ''),
                            created_by=request.user
                        )
                        
                        items_received += 1
                    
                    # Check if this item is fully received
                    if item.quantity_received < item.quantity_ordered:
                        all_received = False
                
                if items_received == 0:
                    return JsonResponse({
                        'success': False,
                        'error': 'يجب استلام عنصر واحد على الأقل'
                    })
                
                # Update purchase order status
                if all_received:
                    purchase_order.status = 'completed'
                    purchase_order.actual_delivery_date = received_date
                else:
                    purchase_order.status = 'in_delivery'
                
                purchase_order.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'تم استلام {items_received} عنصر بنجاح وإضافتها للمخزون',
                    'redirect_url': reverse('suppliers:purchase_order_detail', kwargs={'pk': pk})
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'حدث خطأ أثناء الاستلام: {str(e)}'
            })
    
    # GET request - show form
    from warehouses.models import Warehouse
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'purchase_order': purchase_order,
        'items': items,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    
    return render(request, 'suppliers/purchase_order_receive.html', context)

@login_required
@require_http_methods(["GET"])
def products_api(request):
    """API لجلب المنتجات"""
    query = request.GET.get('q', '')
    
    products = Product.objects.filter(is_active=True)
    
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )
    
    products = products[:50]  # Limit to 50 products
    
    data = [{
        'id': product.id,
        'name': product.name,
        'code': product.code,
        'unit': product.get_unit_display(),
        'cost_price': float(product.cost_price),
    } for product in products]
    
    return JsonResponse({'products': data})



@require_http_methods(["POST"])
def purchase_order_approve(request, pk):
    """الموافقة على أمر الشراء"""
    purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if purchase_order.status == 'draft':
        purchase_order.status = 'approved'
        purchase_order.approved_by = request.user
        purchase_order.approved_at = timezone.now()
        purchase_order.save()
        
        messages.success(request, 'تم الموافقة على أمر الشراء')
        return JsonResponse({'success': True, 'status': 'approved'})
    
    return JsonResponse({'success': False, 'error': 'لا يمكن الموافقة على هذا الأمر'})

def generate_delivery_number():
    """توليد رقم تسليم جديد"""
    today = timezone.now().date()
    prefix = f"DEL{today.strftime('%Y%m%d')}"
    
    last_delivery = PurchaseOrderDelivery.objects.filter(
        delivery_number__startswith=prefix
    ).order_by('-delivery_number').first()
    
    if last_delivery:
        last_number = int(last_delivery.delivery_number[-4:])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"{prefix}{new_number:04d}"


@login_required
@require_http_methods(["POST"])
def purchase_order_reject(request, pk):
    """رفض أمر الشراء"""
    purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    
    # التحقق من إمكانية الرفض
    if purchase_order.status not in ['draft', 'pending']:
        return JsonResponse({
            'success': False, 
            'error': 'لا يمكن رفض هذا الأمر في الحالة الحالية'
        })
    
    # الحصول على سبب الرفض من البيانات المرسلة
    rejection_reason = request.POST.get('rejection_reason', '')
    
    if not rejection_reason:
        return JsonResponse({
            'success': False,
            'error': 'يرجى إدخال سبب الرفض'
        })
    
    try:
        with transaction.atomic():
            # تحديث حالة الأمر
            purchase_order.status = 'cancelled'
            purchase_order.notes = f"{purchase_order.notes}\n\nتم رفض الأمر بواسطة: {request.user.username}\nسبب الرفض: {rejection_reason}\nتاريخ الرفض: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            purchase_order.save()
            
            # إشعار المورد (يمكن إضافة نظام إشعارات هنا)
            
            messages.success(request, 'تم رفض أمر الشراء بنجاح')
            
            return JsonResponse({
                'success': True,
                'message': 'تم رفض أمر الشراء بنجاح',
                'status': 'cancelled'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ أثناء رفض الأمر: {str(e)}'
        })



@require_http_methods(["POST"])
def purchase_order_delete(request, pk):
    """حذف أمر الشراء"""
    purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    
    # التحقق من إمكانية الحذف
    if purchase_order.status not in ['draft', 'cancelled']:
        return JsonResponse({
            'success': False,
            'error': 'لا يمكن حذف هذا الأمر. يمكن حذف الأوامر في حالة مسودة أو ملغية فقط'
        })
    
    # التحقق من وجود دفعات مرتبطة
    if purchase_order.payments.exists():
        return JsonResponse({
            'success': False,
            'error': 'لا يمكن حذف أمر الشراء لوجود دفعات مرتبطة به'
        })
    
    # التحقق من وجود تسليمات مرتبطة
    if purchase_order.deliveries.exists():
        return JsonResponse({
            'success': False,
            'error': 'لا يمكن حذف أمر الشراء لوجود تسليمات مرتبطة به'
        })
    
    try:
        with transaction.atomic():
            po_number = purchase_order.po_number
            supplier_name = purchase_order.supplier.name
            
            # حذف الأمر (سيتم حذف العناصر تلقائياً بسبب CASCADE)
            purchase_order.delete()
            
            messages.success(request, f'تم حذف أمر الشراء {po_number} بنجاح')
            
            return JsonResponse({
                'success': True,
                'message': f'تم حذف أمر الشراء {po_number} بنجاح',
                'redirect_url': reverse('suppliers:purchase_orders')
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ أثناء حذف الأمر: {str(e)}'
        })






@login_required
@require_http_methods(["GET"])
def supplier_search_api(request):
    """البحث عن الموردين - API"""
    query = request.GET.get('q', '')
    suppliers = Supplier.objects.filter(
        Q(name__icontains=query) | Q(code__icontains=query),
        is_active=True
    )[:10]
    
    data = [{
        'id': supplier.id,
        'name': supplier.name,
        'code': supplier.code,
        'type': supplier.get_supplier_type_display(),
    } for supplier in suppliers]
    
    return JsonResponse({'suppliers': data})


@login_required
@require_http_methods(["GET"])
def supplier_stats_api(request, pk):
    """إحصائيات المورد - API"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # إحصائيات الأوامر - Fix the aggregation
    total_orders = supplier.purchase_orders.count()
    completed_orders = supplier.purchase_orders.filter(status='completed').count()
    total_amount = supplier.purchase_orders.filter(status='completed').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    pending_amount = supplier.purchase_orders.filter(
        status__in=['pending', 'approved', 'in_delivery']
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # متوسط التقييم
    avg_rating = supplier.ratings.aggregate(avg=Avg('overall_rating'))['avg'] or 0
    
    data = {
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'total_amount': float(total_amount),
        'pending_amount': float(pending_amount),
        'average_rating': float(avg_rating),
        'completion_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0,
    }
    
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def update_supplier_rating(request, pk):
    """تحديث تقييم المورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # حساب متوسط التقييمات
    avg_rating = supplier.ratings.aggregate(avg=Avg('overall_rating'))['avg']
    if avg_rating:
        supplier.current_rating = avg_rating
        supplier.save()
        
        return JsonResponse({
            'success': True,
            'new_rating': float(avg_rating)
        })
    
    return JsonResponse({'success': False})


@login_required
@require_http_methods(["GET"])
def purchase_order_items_api(request, pk):
    """عناصر أمر الشراء - API"""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    items = [{
        'id': item.id,
        'product_name': item.product.name,
        'quantity_ordered': float(item.quantity_ordered),
        'quantity_received': float(item.quantity_received),
        'quantity_pending': float(item.quantity_pending),
        'unit_price': float(item.unit_price),
        'total_price': float(item.total_price),
        'is_fully_received': item.is_fully_received,
    } for item in order.items.select_related('product')]
    
    return JsonResponse({'items': items})


# Utility Functions
def generate_po_number():
    """توليد رقم أمر شراء جديد"""
    today = timezone.now().date()
    prefix = f"PO{today.strftime('%Y%m%d')}"
    
    last_order = PurchaseOrder.objects.filter(
        po_number__startswith=prefix
    ).order_by('-po_number').first()
    
    if last_order:
        last_number = int(last_order.po_number[-4:])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"{prefix}{new_number:04d}"


def generate_payment_number():
    """توليد رقم دفعة جديد"""
    today = timezone.now().date()
    prefix = f"PAY{today.strftime('%Y%m%d')}"
    
    last_payment = Payment.objects.filter(
        payment_number__startswith=prefix
    ).order_by('-payment_number').first()
    
    if last_payment:
        last_number = int(last_payment.payment_number[-4:])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"{prefix}{new_number:04d}"


# Report Views
class SupplierReportView(LoginRequiredMixin, ListView):
    """تقارير الموردين"""
    model = Supplier
    template_name = 'suppliers/reports.html'
    context_object_name = 'suppliers'
    
    def get_queryset(self):
        return Supplier.objects.filter(is_active=True).annotate(
            total_orders=Count('purchase_orders'),
            completed_orders=Count('purchase_orders', filter=Q(purchase_orders__status='completed')),
            total_amount=Sum('purchase_orders__total_amount', filter=Q(purchase_orders__status='completed')),
            avg_rating=Avg('ratings__overall_rating')
        ).order_by('-total_amount')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # فترة التقرير
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if not date_from:
            date_from = (timezone.now() - timedelta(days=30)).date()
        else:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            
        if not date_to:
            date_to = timezone.now().date()
        else:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        
        context['date_from'] = date_from
        context['date_to'] = date_to
        
        # إحصائيات الفترة
        orders_in_period = PurchaseOrder.objects.filter(
            order_date__date__range=[date_from, date_to]
        )
        
        context['period_stats'] = {
            'total_orders': orders_in_period.count(),
            'completed_orders': orders_in_period.filter(status='completed').count(),
            'total_amount': orders_in_period.filter(status='completed').aggregate(
                total=Sum('total_amount')
            )['total'] or 0,
            'unique_suppliers': orders_in_period.values('supplier').distinct().count(),
        }
        
        # أفضل الموردين في الفترة
        context['top_suppliers_period'] = Supplier.objects.filter(
            purchase_orders__order_date__date__range=[date_from, date_to]
        ).annotate(
            period_orders=Count('purchase_orders', filter=Q(
                purchase_orders__order_date__date__range=[date_from, date_to]
            )),
            period_amount=Sum('purchase_orders__total_amount', filter=Q(
                purchase_orders__order_date__date__range=[date_from, date_to],
                purchase_orders__status='completed'
            ))
        ).filter(period_amount__gt=0).order_by('-period_amount')[:10]
        
        return context


# Export Views
from django.http import HttpResponse
import csv
from django.utils.encoding import smart_str

@login_required
def export_suppliers_csv(request):
    """تصدير الموردين إلى CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="suppliers.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'كود المورد', 'اسم المورد', 'نوع المورد', 'الشخص المسؤول',
        'رقم الهاتف', 'البريد الإلكتروني', 'العنوان', 'حد الائتمان',
        'مدة السداد', 'التقييم الحالي', 'نشط', 'تاريخ الإنشاء'
    ])
    
    suppliers = Supplier.objects.all()
    for supplier in suppliers:
        writer.writerow([
            smart_str(supplier.code),
            smart_str(supplier.name),
            smart_str(supplier.get_supplier_type_display()),
            smart_str(supplier.contact_person),
            smart_str(supplier.phone),
            smart_str(supplier.email),
            smart_str(supplier.address),
            smart_str(supplier.credit_limit),
            smart_str(supplier.payment_terms_days),
            smart_str(supplier.current_rating),
            'نعم' if supplier.is_active else 'لا',
            smart_str(supplier.created_at.strftime('%Y-%m-%d')),
        ])
    
    return response


@login_required
def export_purchase_orders_csv(request):
    """تصدير أوامر الشراء إلى CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="purchase_orders.csv"'
    response.write('\ufeff')  # BOM for UTF-8
    
    writer = csv.writer(response)
    writer.writerow([
        'رقم الأمر', 'المورد', 'تاريخ الأمر', 'تاريخ التسليم المتوقع',
        'تاريخ التسليم الفعلي', 'الحالة', 'الأولوية', 'المبلغ الإجمالي',
        'أنشأ بواسطة', 'تاريخ الإنشاء'
    ])
    
    orders = PurchaseOrder.objects.select_related('supplier', 'created_by').all()
    for order in orders:
        writer.writerow([
            smart_str(order.po_number),
            smart_str(order.supplier.name),
            smart_str(order.order_date.strftime('%Y-%m-%d')),
            smart_str(order.expected_delivery_date.strftime('%Y-%m-%d')),
            smart_str(order.actual_delivery_date.strftime('%Y-%m-%d') if order.actual_delivery_date else ''),
            smart_str(order.get_status_display()),
            smart_str(order.get_priority_display()),
            smart_str(order.total_amount),
            smart_str(order.created_by.username if order.created_by else ''),
            smart_str(order.created_at.strftime('%Y-%m-%d')),
        ])
    
    return response


# Bulk Operations
@login_required
@require_http_methods(["POST"])
def bulk_update_suppliers(request):
    """تحديث مجموعي للموردين"""
    supplier_ids = request.POST.getlist('supplier_ids')
    action = request.POST.get('action')
    
    if not supplier_ids or not action:
        return JsonResponse({'success': False, 'error': 'بيانات غير مكتملة'})
    
    suppliers = Supplier.objects.filter(id__in=supplier_ids)
    
    if action == 'activate':
        suppliers.update(is_active=True)
        message = f'تم تفعيل {suppliers.count()} مورد'
    elif action == 'deactivate':
        suppliers.update(is_active=False)
        message = f'تم إلغاء تفعيل {suppliers.count()} مورد'
    else:
        return JsonResponse({'success': False, 'error': 'عملية غير صحيحة'})
    
    return JsonResponse({'success': True, 'message': message})


# Advanced Search and Filtering
class AdvancedSupplierSearchView(LoginRequiredMixin, ListView):
    """البحث المتقدم في الموردين"""
    model = Supplier
    template_name = 'suppliers/advanced_search.html'
    context_object_name = 'suppliers'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        
        # البحث النصي
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(contact_person__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        # فلترة حسب النوع
        supplier_types = self.request.GET.getlist('supplier_type')
        if supplier_types:
            queryset = queryset.filter(supplier_type__in=supplier_types)
        
        # فلترة حسب التقييم
        min_rating = self.request.GET.get('min_rating')
        max_rating = self.request.GET.get('max_rating')
        if min_rating:
            queryset = queryset.filter(current_rating__gte=min_rating)
        if max_rating:
            queryset = queryset.filter(current_rating__lte=max_rating)
        
        # فلترة حسب حد الائتمان
        min_credit = self.request.GET.get('min_credit')
        max_credit = self.request.GET.get('max_credit')
        if min_credit:
            queryset = queryset.filter(credit_limit__gte=min_credit)
        if max_credit:
            queryset = queryset.filter(credit_limit__lte=max_credit)
        
        # فلترة حسب تاريخ الإنشاء
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        # فلترة حسب طرق الدفع
        payment_methods = self.request.GET.getlist('payment_method')
        if payment_methods:
            for method in payment_methods:
                queryset = queryset.filter(supported_payment_methods__contains=method)
        
        # الترتيب
        sort_by = self.request.GET.get('sort_by', 'name')
        sort_order = self.request.GET.get('sort_order', 'asc')
        
        if sort_order == 'desc':
            sort_by = f'-{sort_by}'
        
        return queryset.order_by(sort_by)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplier_types'] = Supplier.SUPPLIER_TYPES
        context['payment_methods'] = Supplier.PAYMENT_METHODS
        context['filters'] = {
            'search': self.request.GET.get('search', ''),
            'supplier_type': self.request.GET.getlist('supplier_type'),
            'min_rating': self.request.GET.get('min_rating', ''),
            'max_rating': self.request.GET.get('max_rating', ''),
            'min_credit': self.request.GET.get('min_credit', ''),
            'max_credit': self.request.GET.get('max_credit', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
            'payment_method': self.request.GET.getlist('payment_method'),
            'sort_by': self.request.GET.get('sort_by', 'name'),
            'sort_order': self.request.GET.get('sort_order', 'asc'),
        }
        return context

# Add this function to your views.py file
@login_required
@require_http_methods(["POST"])
def toggle_supplier_status(request, pk):
    """تغيير حالة المورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    supplier.is_active = not supplier.is_active
    supplier.save()
    
    return JsonResponse({
        'success': True,
        'is_active': supplier.is_active,
        'message': 'تم تحديث حالة المورد بنجاح'
    })


class SupplierRatingCreateView(LoginRequiredMixin, CreateView):
    """إنشاء تقييم جديد للمورد"""
    model = SupplierRating
    form_class = SupplierRatingForm
    template_name = 'suppliers/supplier_rating_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier_id = self.kwargs.get('supplier_id')
        purchase_order_id = self.kwargs.get('purchase_order_id')
        
        if supplier_id:
            context['supplier'] = get_object_or_404(Supplier, pk=supplier_id)
        if purchase_order_id:
            context['purchase_order'] = get_object_or_404(PurchaseOrder, pk=purchase_order_id)
            context['supplier'] = context['purchase_order'].supplier
            
        return context
    
    def form_valid(self, form):
        supplier_id = self.kwargs.get('supplier_id')
        purchase_order_id = self.kwargs.get('purchase_order_id')
        
        if purchase_order_id:
            purchase_order = get_object_or_404(PurchaseOrder, pk=purchase_order_id)
            form.instance.purchase_order = purchase_order
            form.instance.supplier = purchase_order.supplier
        elif supplier_id:
            form.instance.supplier = get_object_or_404(Supplier, pk=supplier_id)
            
        form.instance.rated_by = self.request.user
        
        messages.success(self.request, 'تم إضافة التقييم بنجاح')
        return super().form_valid(form)
    
    def get_success_url(self):
        if self.object.purchase_order:
            return reverse_lazy('suppliers:purchase_order_detail', kwargs={'pk': self.object.purchase_order.pk})
        else:
            return reverse_lazy('suppliers:supplier_detail', kwargs={'pk': self.object.supplier.pk})


class SupplierRatingListView(LoginRequiredMixin, ListView):
    """عرض قائمة تقييمات المورد"""
    model = SupplierRating
    template_name = 'suppliers/supplier_rating_list.html'
    context_object_name = 'ratings'
    paginate_by = 20
    
    def get_queryset(self):
        supplier_id = self.kwargs.get('supplier_id')
        if supplier_id:
            return SupplierRating.objects.filter(
                supplier_id=supplier_id
            ).select_related('supplier', 'purchase_order', 'rated_by').order_by('-rating_date')
        return SupplierRating.objects.select_related(
            'supplier', 'purchase_order', 'rated_by'
        ).order_by('-rating_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier_id = self.kwargs.get('supplier_id')
        if supplier_id:
            context['supplier'] = get_object_or_404(Supplier, pk=supplier_id)
            
            # إحصائيات التقييم
            ratings = context['ratings']
            if ratings:
                context['rating_stats'] = {
                    'total_ratings': ratings.count(),
                    'average_rating': ratings.aggregate(avg=Avg('overall_rating'))['avg'] or 0,
                    'quality_avg': ratings.aggregate(avg=Avg('quality_rating'))['avg'] or 0,
                    'delivery_avg': ratings.aggregate(avg=Avg('delivery_rating'))['avg'] or 0,
                    'price_avg': ratings.aggregate(avg=Avg('price_rating'))['avg'] or 0,
                    'service_avg': ratings.aggregate(avg=Avg('service_rating'))['avg'] or 0,
                    'communication_avg': ratings.aggregate(avg=Avg('communication_rating'))['avg'] or 0,
                }
        return context
    
    

class SupplierRatingDetailView(LoginRequiredMixin, DetailView):
    """عرض تفاصيل التقييم"""
    model = SupplierRating
    template_name = 'suppliers/supplier_rating_detail.html'
    context_object_name = 'rating'

class SupplierRatingUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل التقييم"""
    model = SupplierRating
    form_class = SupplierRatingForm
    template_name = 'suppliers/supplier_rating_form.html'
    
    def get_queryset(self):
        # المستخدم يمكنه تعديل تقييماته فقط أو المدراء يمكنهم تعديل أي تقييم
        if self.request.user.is_superuser or hasattr(self.request.user, 'role') and self.request.user.role in ['admin', 'manager']:
            return SupplierRating.objects.all()
        return SupplierRating.objects.filter(rated_by=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث التقييم بنجاح')
        return super().form_valid(form)
    
    def get_success_url(self):
        if self.object.purchase_order:
            return reverse_lazy('suppliers:purchase_order_detail', kwargs={'pk': self.object.purchase_order.pk})
        else:
            return reverse_lazy('suppliers:supplier_detail', kwargs={'pk': self.object.supplier.pk})

class SupplierRatingDeleteView(LoginRequiredMixin, DeleteView):
    """حذف التقييم"""
    model = SupplierRating
    template_name = 'suppliers/supplier_rating_confirm_delete.html'
    
    def get_queryset(self):
        # المستخدم يمكنه حذف تقييماته فقط أو المدراء يمكنهم حذف أي تقييم
        if self.request.user.is_superuser or hasattr(self.request.user, 'role') and self.request.user.role in ['admin', 'manager']:
            return SupplierRating.objects.all()
        return SupplierRating.objects.filter(rated_by=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف التقييم بنجاح')
        return super().delete(request, *args, **kwargs)
    
    def get_success_url(self):
        if self.object.purchase_order:
            return reverse_lazy('suppliers:purchase_order_detail', kwargs={'pk': self.object.purchase_order.pk})
        else:
            return reverse_lazy('suppliers:supplier_detail', kwargs={'pk': self.object.supplier.pk})


@login_required
@require_http_methods(["POST"])
def quick_supplier_rating(request, supplier_id):
    """تقييم سريع للمورد"""
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    try:
        overall_rating = float(request.POST.get('overall_rating', 0))
        comments = request.POST.get('comments', '')
        
        if overall_rating < 1 or overall_rating > 5:
            return JsonResponse({
                'success': False,
                'error': 'التقييم يجب أن يكون بين 1 و 5'
            })
        
        # إنشاء تقييم سريع
        rating = SupplierRating.objects.create(
            supplier=supplier,
            quality_rating=int(overall_rating),
            delivery_rating=int(overall_rating),
            price_rating=int(overall_rating),
            service_rating=int(overall_rating),
            communication_rating=int(overall_rating),
            overall_rating=overall_rating,
            comments=comments,
            rated_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': 'تم إضافة التقييم بنجاح',
            'rating_id': rating.id,
            'new_average': float(supplier.current_rating)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["GET"])
def supplier_rating_stats_api(request, supplier_id):
    """إحصائيات تقييم المورد - API"""
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    ratings = supplier.ratings.all()
    
    if not ratings.exists():
        return JsonResponse({
            'total_ratings': 0,
            'average_rating': 0,
            'rating_distribution': {str(i): 0 for i in range(1, 6)},
            'criteria_averages': {
                'quality': 0,
                'delivery': 0,
                'price': 0,
                'service': 0,
                'communication': 0
            }
        })
    
    # توزيع التقييمات
    rating_distribution = {}
    for i in range(1, 6):
        count = ratings.filter(overall_rating__gte=i, overall_rating__lt=i+1).count()
        rating_distribution[str(i)] = count
    
    # متوسط كل معيار
    criteria_averages = {
        'quality': ratings.aggregate(avg=Avg('quality_rating'))['avg'] or 0,
        'delivery': ratings.aggregate(avg=Avg('delivery_rating'))['avg'] or 0,
        'price': ratings.aggregate(avg=Avg('price_rating'))['avg'] or 0,
        'service': ratings.aggregate(avg=Avg('service_rating'))['avg'] or 0,
        'communication': ratings.aggregate(avg=Avg('communication_rating'))['avg'] or 0,
    }
    
    return JsonResponse({
        'total_ratings': ratings.count(),
        'average_rating': float(supplier.current_rating),
        'rating_distribution': rating_distribution,
        'criteria_averages': {k: float(v) for k, v in criteria_averages.items()}
    })
    
# Add these API views to the existing views.py

@login_required
@require_http_methods(["GET"])
def supplier_rating_analytics_api(request):
    """تحليلات التقييمات - API"""
    from .utils import get_supplier_rating_analytics
    
    try:
        analytics = get_supplier_rating_analytics()
        return JsonResponse(analytics)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ في جلب التحليلات: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def bulk_rate_suppliers(request):
    """تقييم مجموعي للموردين"""
    try:
        supplier_ratings = request.POST.get('ratings')  # JSON string
        if not supplier_ratings:
            return JsonResponse({
                'success': False,
                'error': 'بيانات التقييم مطلوبة'
            })
        
        import json
        ratings_data = json.loads(supplier_ratings)
        
        created_ratings = []
        errors = []
        
        with transaction.atomic():
            for rating_data in ratings_data:
                # Validate data
                from .utils import validate_rating_data
                validation_errors = validate_rating_data(rating_data)
                
                if validation_errors:
                    errors.extend(validation_errors)
                    continue
                
                # Create rating
                rating = SupplierRating.objects.create(
                    supplier_id=rating_data['supplier_id'],
                    purchase_order_id=rating_data.get('purchase_order_id'),
                    quality_rating=rating_data['quality_rating'],
                    delivery_rating=rating_data['delivery_rating'],
                    price_rating=rating_data['price_rating'],
                    service_rating=rating_data['service_rating'],
                    communication_rating=rating_data['communication_rating'],
                    comments=rating_data.get('comments', ''),
                    season=rating_data.get('season', ''),
                    rated_by=request.user
                )
                created_ratings.append(rating.id)
        
        if errors:
            return JsonResponse({
                'success': False,
                'errors': errors,
                'created_count': len(created_ratings)
            })
        
        return JsonResponse({
            'success': True,
            'message': f'تم إنشاء {len(created_ratings)} تقييم بنجاح',
            'created_ratings': created_ratings
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["GET"])
def supplier_comparison_api(request):
    """مقارنة الموردين - API"""
    supplier_ids = request.GET.getlist('supplier_ids')
    
    if not supplier_ids:
        return JsonResponse({
            'success': False,
            'error': 'يجب تحديد موردين على الأقل للمقارنة'
        })
    
    try:
        from .utils import get_supplier_comparison
        comparison_data = get_supplier_comparison(supplier_ids)
        
        return JsonResponse({
            'success': True,
            'comparison': comparison_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ في المقارنة: {str(e)}'
        })
@login_required
@require_http_methods(["GET"])
def rating_suggestions_api(request):
    """اقتراحات التقييم - API"""
    try:
        from .utils import suggest_suppliers_for_rating
        suggestions = suggest_suppliers_for_rating()
        
        # Format data for JSON response
        formatted_suggestions = []
        for suggestion in suggestions:
            formatted_suggestions.append({
                'supplier': {
                    'id': suggestion['supplier'].id,
                    'name': suggestion['supplier'].name,
                    'code': suggestion['supplier'].code
                },
                'order': {
                    'id': suggestion['order'].id,
                    'po_number': suggestion['order'].po_number,
                    'completion_date': suggestion['order'].actual_delivery_date.strftime('%Y-%m-%d'),
                    'total_amount': float(suggestion['order'].total_amount)
                },
                'days_since_completion': suggestion['days_since_completion'],
                'priority': suggestion['priority']
            })
        
        return JsonResponse({
            'success': True,
            'suggestions': formatted_suggestions
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ في جلب الاقتراحات: {str(e)}'
        })

@login_required
@require_http_methods(["GET"])
def export_ratings_csv_api(request):
    """تصدير التقييمات CSV - API"""
    try:
        supplier_ids = request.GET.getlist('supplier_ids')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        # Parse dates
        if date_from:
            from datetime import datetime
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        if date_to:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        
        from .utils import export_supplier_ratings_report
        csv_content = export_supplier_ratings_report(
            supplier_ids=supplier_ids if supplier_ids else None,
            date_from=date_from,
            date_to=date_to
        )
        
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="supplier_ratings.csv"'
        response.write('\ufeff')  # BOM for UTF-8
        
        return response
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'حدث خطأ في التصدير: {str(e)}'
        })
