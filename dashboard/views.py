from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from users.models import User
from warehouses.models import Product, StockItem, StockMovement
from suppliers.models import Supplier, PurchaseOrder
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db import models
from django.views.decorators.cache import cache_page

@login_required
@cache_page(60 * 15) # Cache the view for 15 minutes
def index(request):
    """Dashboard main page with statistics"""
    
    # Get current date and calculate date ranges
    today = timezone.now().date()
    last_30_days = today - timedelta(days=30)
    
    # User Statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    new_users_this_month = User.objects.filter(
        date_joined__date__gte=last_30_days
    ).count()
    users_by_role = User.objects.values('role').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Product Statistics
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    
    # Get low stock products --- OPTIMIZED QUERY ---
    try:
        low_stock_products = StockItem.objects.select_related('product').filter(
            quantity__lte=F('product__min_stock_level')
        ).count()
    except Exception:
        low_stock_products = 0
    
    # Get best products by stock quantity
    try:
        best_products = StockItem.objects.select_related('product').order_by('-quantity')[:5]
    except Exception:
        best_products = []
    
    # Recent stock movements
    try:
        recent_movements = StockMovement.objects.select_related(
            'stock_item__product', 'created_by'
        ).order_by('-created_at')[:10]
    except Exception:
        recent_movements = []
    
    # Supplier Statistics
    total_suppliers = Supplier.objects.count()
    active_suppliers = Supplier.objects.filter(is_active=True).count()
    
    # Purchase Order Statistics
    total_purchase_orders = PurchaseOrder.objects.count()
    pending_orders = PurchaseOrder.objects.filter(status='pending').count()
    completed_orders = PurchaseOrder.objects.filter(status='completed').count()
    overdue_orders = PurchaseOrder.objects.filter(
        expected_delivery_date__lt=today,
        status__in=['pending', 'approved', 'in_delivery']
    ).count()
    
    # Recent Purchase Orders
    recent_purchase_orders = PurchaseOrder.objects.select_related(
        'supplier'
    ).order_by('-created_at')[:5]
    
    # Monthly statistics for charts
    monthly_users = []
    monthly_orders = []
    for i in range(6):
        month_start = today.replace(day=1) - timedelta(days=30*i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        users_count = User.objects.filter(
            date_joined__date__range=[month_start, month_end]
        ).count()
        
        orders_count = PurchaseOrder.objects.filter(
            created_at__date__range=[month_start, month_end]
        ).count()
        
        monthly_users.append({
            'month': month_start.strftime('%B'),
            'count': users_count
        })
        
        monthly_orders.append({
            'month': month_start.strftime('%B'),
            'count': orders_count
        })
    
    monthly_users.reverse()
    monthly_orders.reverse()
    
    context = {
        'total_users': total_users,
        'active_users': active_users,
        'new_users_this_month': new_users_this_month,
        'users_by_role': users_by_role,
        'total_products': total_products,
        'active_products': active_products,
        'low_stock_products': low_stock_products,
        'best_products': best_products,
        'recent_movements': recent_movements,
        'total_suppliers': total_suppliers,
        'active_suppliers': active_suppliers,
        'total_purchase_orders': total_purchase_orders,
        'pending_orders': pending_orders,
        'completed_orders': completed_orders,
        'overdue_orders': overdue_orders,
        'recent_purchase_orders': recent_purchase_orders,
        'monthly_users': monthly_users,
        'monthly_orders': monthly_orders,
    }
    
    return render(request, 'dashboard/index.html', context)

@login_required
def sales_report(request):
    """Sales report view"""
    return render(request, 'dashboard/reports/sales.html')

@login_required
def inventory_report(request):
    """Inventory report view"""
    return render(request, 'dashboard/reports/inventory.html')

@login_required
def production_report(request):
    """Production report view"""
    return render(request, 'dashboard/reports/production.html')

@login_required
def financial_report(request):
    """Financial report view"""
    return render(request, 'dashboard/reports/financial.html')
