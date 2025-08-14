from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, F, Avg, DecimalField, Max, Min, Value, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
import json
from decimal import Decimal

# Import models from all relevant apps
from warehouses.models import Product, StockItem, Warehouse
from production.models import ProductionOrder, AssemblyProcess, FinishingProcess, ExternalManufacturer, CuttingProcess, CutPiece, BillOfMaterials
from hr.models import Employee, Attendance, Department

@login_required
def index(request):
    """
    Dashboard main page with comprehensive statistics.
    """
    today = timezone.now().date()
    last_30_days = today - timedelta(days=30)
    
    # --- HR Statistics ---
    total_employees = Employee.objects.filter(is_active=True).count()
    try:
        attended_today_count = Attendance.objects.filter(date=today, check_in__isnull=False).count()
    except Exception:
        attended_today_count = 0
    on_leave_or_absent = total_employees - attended_today_count
    departments_data = list(Employee.objects.filter(is_active=True).values('department__name').annotate(count=Count('id')).order_by('-count'))

    # --- Warehouse Statistics ---
    total_products = Product.objects.filter(is_active=True).count()
    low_stock_products_count = StockItem.objects.filter(
        quantity__lte=F('product__min_stock_level'), 
        product__min_stock_level__gt=0
    ).count()
    total_stock_value = StockItem.objects.annotate(
        item_value=F('quantity') * F('product__cost_price')
    ).aggregate(
        total_value=Coalesce(Sum('item_value'), 0, output_field=DecimalField())
    )['total_value']
    warehouses_summary = Warehouse.objects.annotate(
        num_items=Count('stock_items', distinct=True),
        total_quantity=Coalesce(Sum('stock_items__quantity'), 0, output_field=DecimalField())
    ).order_by('-total_quantity')[:5]

    # --- Production Statistics ---
    active_orders_count = ProductionOrder.objects.filter(is_active=True, status__in=['approved', 'in_cutting', 'in_assembly', 'in_dyeing', 'in_finishing']).count()
    completed_this_month = ProductionOrder.objects.filter(status='completed', actual_completion_date__gte=last_30_days).count()
    orders_by_status = list(ProductionOrder.objects.values('status').annotate(count=Count('id')).order_by('-count'))
    total_defects_assembly = AssemblyProcess.objects.aggregate(total=Coalesce(Sum('defects_count'), 0))['total']
    total_pieces_sent_assembly = AssemblyProcess.objects.aggregate(total=Coalesce(Sum('quantity_sent'), 0))['total']
    defect_rate = (total_defects_assembly / total_pieces_sent_assembly * 100) if total_pieces_sent_assembly > 0 else 0
    recent_production_orders = ProductionOrder.objects.select_related('product').order_by('-created_at')[:5]

    # --- Cutting and Meterage Analysis ---
    total_pieces_cut = CuttingProcess.objects.aggregate(total=Coalesce(Sum('total_pieces_cut'), 0))['total']
    
    product_search_id = request.GET.get('product_id')
    selected_product = None
    product_orders = None
    total_quantity_ordered_for_product = 0 # Initialize
    
    meterage_query = CuttingProcess.objects.filter(total_pieces_cut__gt=0, total_fabric_used__gt=0)
    
    if product_search_id:
        try:
            selected_product = Product.objects.get(pk=product_search_id)
            meterage_query = meterage_query.filter(production_order__product=selected_product)
            product_orders = ProductionOrder.objects.filter(product=selected_product).order_by('-created_at')

            # NEW: Calculate total quantity ordered for the selected product
            if product_orders:
                total_quantity_ordered_for_product = product_orders.aggregate(
                    total=Coalesce(Sum('quantity_ordered'), 0)
                )['total']

        except (Product.DoesNotExist, ValueError):
            product_search_id = None

    meterage_stats = meterage_query.annotate(
        actual_meterage=ExpressionWrapper(
            F('total_fabric_used') / F('total_pieces_cut'),
            output_field=DecimalField()
        )
    ).aggregate(
        highest_meterage=Coalesce(Max('actual_meterage'), Value(0), output_field=DecimalField()),
        lowest_meterage=Coalesce(Min('actual_meterage'), Value(0), output_field=DecimalField())
    )

    context = {
        'total_employees': total_employees, 'attended_today_count': attended_today_count,
        'on_leave_or_absent': on_leave_or_absent,
        'departments_data': departments_data, 'total_products': total_products,
        'low_stock_products_count': low_stock_products_count, 'total_stock_value': total_stock_value,
        'warehouses_summary': warehouses_summary,
        'active_orders_count': active_orders_count, 'completed_this_month': completed_this_month,
        'orders_by_status': orders_by_status, 'defect_rate': defect_rate,
        'recent_production_orders': recent_production_orders, 'total_pieces_cut': total_pieces_cut,
        'selected_product': selected_product, 'meterage_stats': meterage_stats,
        'product_search_id': product_search_id,
        'total_quantity_ordered_for_product': total_quantity_ordered_for_product, # Changed variable
        'product_orders': product_orders,
        'today_date': today,
    }
    
    return render(request, 'dashboard/index.html', context)

@login_required
def product_search_ajax(request):
    """
    Handles AJAX requests for searching finished products.
    """
    term = request.GET.get('term', '')
    if len(term) < 2:
        return JsonResponse([], safe=False)
    
    products = Product.objects.filter(
        product_type='finished',
        is_active=True,
        name__icontains=term
    ).values('id', 'name', 'code')[:10]
    
    return JsonResponse(list(products), safe=False)


# Placeholder report views
@login_required
def sales_report(request): return render(request, 'dashboard/reports/sales.html')
@login_required
def inventory_report(request): return render(request, 'dashboard/reports/inventory.html')
@login_required
def production_report(request): return render(request, 'dashboard/reports/production.html')
@login_required
def financial_report(request): return render(request, 'dashboard/reports/financial.html')
