# production/blueprints/category_size_blueprint.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
import csv

# --- Model and Form Imports ---
from warehouses.models import Category as WarehouseCategory, Product
from ..models import SizeGroup
from warehouses.forms import CategoryForm
from ..forms import SizeGroupForm

# =============================================================================
#  MAIN MANAGEMENT VIEW
# =============================================================================

@login_required
def category_size_management_view(request):
    """
    Displays the combined management page for product categories and size groups,
    powering the UI with AJAX.
    """
    # Get categories with pagination
    categories_list = WarehouseCategory.objects.all().order_by('name')
    category_paginator = Paginator(categories_list, 10)
    category_page_number = request.GET.get('category_page', 1)
    categories_page_obj = category_paginator.get_page(category_page_number)
    
    # Get size groups with pagination
    size_groups_list = SizeGroup.objects.all().order_by('name')
    size_paginator = Paginator(size_groups_list, 10)
    size_page_number = request.GET.get('size_page', 1)
    size_groups_page_obj = size_paginator.get_page(size_page_number)
    
    # Forms for creating new entries in the modals
    category_form = CategoryForm()
    size_group_form = SizeGroupForm()
    
    context = {
        'categories': categories_page_obj,
        'size_groups': size_groups_page_obj,
        'category_form': category_form,
        'size_group_form': size_group_form,
        'parent_categories': WarehouseCategory.objects.filter(is_active=True),
    }
    
    return render(request, 'production/category_size_management.html', context)

# =============================================================================
#  AJAX VIEWS FOR CATEGORY
# =============================================================================

@login_required
@require_http_methods(["POST"])
def create_category_ajax(request):
    """Creates a new Category via an AJAX request."""
    form = CategoryForm(request.POST)
    if form.is_valid():
        category = form.save()
        return JsonResponse({
            'success': True,
            'message': 'تم إنشاء الفئة بنجاح',
            'category': {'id': category.id, 'name': category.name, 'is_active': category.is_active}
        })
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@login_required
@require_http_methods(["POST"])
def update_category_ajax(request, category_id):
    """Updates a Category via an AJAX request."""
    category = get_object_or_404(WarehouseCategory, id=category_id)
    form = CategoryForm(request.POST, instance=category)
    if form.is_valid():
        category = form.save()
        return JsonResponse({
            'success': True,
            'message': 'تم تحديث الفئة بنجاح',
            'category': {'id': category.id, 'name': category.name, 'is_active': category.is_active}
        })
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@login_required
@require_http_methods(["POST"])
def delete_category_ajax(request, category_id):
    """Deletes a Category via AJAX after checking for usage."""
    category = get_object_or_404(WarehouseCategory, id=category_id)
    if Product.objects.filter(category=category).exists():
        return JsonResponse({
            'success': False,
            'message': 'لا يمكن حذف الفئة لأنها مستخدمة في منتجات حالية.'
        }, status=400)
    
    category_name = category.name
    category.delete()
    return JsonResponse({'success': True, 'message': f'تم حذف الفئة "{category_name}" بنجاح'})

@login_required
def get_category_ajax(request, category_id):
    """Fetches data for a single Category to populate an edit modal."""
    category = get_object_or_404(WarehouseCategory, id=category_id)
    return JsonResponse({
        'success': True,
        'category': {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'is_active': category.is_active,
        }
    })
    
@login_required
@require_http_methods(["POST"])
def toggle_category_status_ajax(request, category_id):
    """Toggles the 'is_active' status of a Category."""
    category = get_object_or_404(WarehouseCategory, id=category_id)
    category.is_active = not category.is_active
    category.save()
    return JsonResponse({
        'success': True, 
        'message': f'تم {"تفعيل" if category.is_active else "إلغاء تفعيل"} الفئة بنجاح',
        'is_active': category.is_active
    })

# =============================================================================
#  AJAX VIEWS FOR SIZE GROUP
# =============================================================================

@login_required
@require_http_methods(["POST"])
def create_size_group_ajax(request):
    """Creates a new SizeGroup via an AJAX request."""
    form = SizeGroupForm(request.POST)
    if form.is_valid():
        size_group = form.save()
        return JsonResponse({
            'success': True,
            'message': 'تم إنشاء مجموعة المقاسات بنجاح',
            'size_group': {'id': size_group.id, 'name': size_group.name, 'sizes': size_group.sizes}
        })
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@login_required
@require_http_methods(["POST"])
def update_size_group_ajax(request, size_group_id):
    """Updates an existing SizeGroup via an AJAX request."""
    size_group = get_object_or_404(SizeGroup, id=size_group_id)
    form = SizeGroupForm(request.POST, instance=size_group)
    if form.is_valid():
        size_group = form.save()
        return JsonResponse({
            'success': True,
            'message': 'تم تحديث مجموعة المقاسات بنجاح',
            'size_group': {'id': size_group.id, 'name': size_group.name, 'sizes': size_group.sizes}
        })
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@login_required
@require_http_methods(["POST"])
def delete_size_group_ajax(request, size_group_id):
    """Deletes a SizeGroup via an AJAX request after checking for usage."""
    size_group = get_object_or_404(SizeGroup, id=size_group_id)
    if Product.objects.filter(size_group=size_group).exists():
        return JsonResponse({
            'success': False,
            'message': 'لا يمكن حذف مجموعة المقاسات لأنها مستخدمة في منتجات حالية.'
        }, status=400)
    
    size_group_name = size_group.name
    size_group.delete()
    return JsonResponse({'success': True, 'message': f'تم حذف مجموعة المقاسات "{size_group_name}" بنجاح'})

@login_required
def get_size_group_ajax(request, size_group_id):
    """Fetches data for a single SizeGroup to populate an edit modal."""
    size_group = get_object_or_404(SizeGroup, id=size_group_id)
    return JsonResponse({
        'success': True,
        'size_group': {
            'id': size_group.id,
            'name': size_group.name,
            'sizes': ", ".join(size_group.sizes),
        }
    })

# =============================================================================
#  EXPORT VIEWS
# =============================================================================

@login_required
def export_size_groups(request):
    """Exports all Size Groups to a CSV file."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="size_groups_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'اسم المجموعة', 'المقاسات', 'عدد المنتجات المستخدمة'])
    
    for size_group in SizeGroup.objects.all().order_by('name'):
        writer.writerow([
            size_group.id,
            size_group.name,
            ', '.join(size_group.sizes),
            Product.objects.filter(size_group=size_group).count()
        ])
    return response

@login_required
def export_categories(request):
    """Exports Categories to a CSV file."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="categories_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'اسم الفئة', 'الوصف', 'الحالة', 'عدد المنتجات'])
    
    for category in WarehouseCategory.objects.all().order_by('name'):
        writer.writerow([
            category.id,
            category.name,
            category.description,
            'نشط' if category.is_active else 'غير نشط',
            Product.objects.filter(category=category).count()
        ])
    return response
