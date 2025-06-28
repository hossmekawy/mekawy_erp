from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse,HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from ..models import ProductCategory, SizeGroup
from ..forms import ProductCategoryForm, SizeGroupForm
import json
import csv
from django.utils import timezone

@login_required
def category_size_management_view(request):
    """صفحة إدارة الفئات ومجموعات المقاسات"""
    # Get categories with pagination
    categories = ProductCategory.objects.all().order_by('name')
    category_paginator = Paginator(categories, 10)
    category_page = request.GET.get('category_page', 1)
    categories_page_obj = category_paginator.get_page(category_page)
    
    # Get size groups with pagination
    size_groups = SizeGroup.objects.all().order_by('name')
    size_paginator = Paginator(size_groups, 10)
    size_page = request.GET.get('size_page', 1)
    size_groups_page_obj = size_paginator.get_page(size_page)
    
    # Forms
    category_form = ProductCategoryForm()
    size_group_form = SizeGroupForm()
    
    context = {
        'categories': categories_page_obj,
        'size_groups': size_groups_page_obj,
        'category_form': category_form,
        'size_group_form': size_group_form,
        'parent_categories': ProductCategory.objects.filter(parent__isnull=True, is_active=True),
    }
    
    return render(request, 'production/category_size_management.html', context)

@login_required
@require_http_methods(["POST"])
def create_category_ajax(request):
    """إنشاء فئة جديدة عبر AJAX"""
    try:
        form = ProductCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            return JsonResponse({
                'success': True,
                'message': 'تم إنشاء الفئة بنجاح',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'parent': category.parent.name if category.parent else None,
                    'is_active': category.is_active,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'خطأ في البيانات',
                'errors': form.errors
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def create_size_group_ajax(request):
    """إنشاء مجموعة مقاسات جديدة عبر AJAX"""
    try:
        form = SizeGroupForm(request.POST)
        if form.is_valid():
            size_group = form.save()
            return JsonResponse({
                'success': True,
                'message': 'تم إنشاء مجموعة المقاسات بنجاح',
                'size_group': {
                    'id': size_group.id,
                    'name': size_group.name,
                    'sizes': size_group.sizes,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'خطأ في البيانات',
                'errors': form.errors
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def update_category_ajax(request, category_id):
    """تحديث فئة عبر AJAX"""
    try:
        category = get_object_or_404(ProductCategory, id=category_id)
        form = ProductCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            return JsonResponse({
                'success': True,
                'message': 'تم تحديث الفئة بنجاح',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'parent': category.parent.name if category.parent else None,
                    'is_active': category.is_active,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'خطأ في البيانات',
                'errors': form.errors
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def update_size_group_ajax(request, size_group_id):
    """تحديث مجموعة مقاسات عبر AJAX"""
    try:
        size_group = get_object_or_404(SizeGroup, id=size_group_id)
        form = SizeGroupForm(request.POST, instance=size_group)
        if form.is_valid():
            size_group = form.save()
            return JsonResponse({
                'success': True,
                'message': 'تم تحديث مجموعة المقاسات بنجاح',
                'size_group': {
                    'id': size_group.id,
                    'name': size_group.name,
                    'sizes': size_group.sizes,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'خطأ في البيانات',
                'errors': form.errors
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def delete_category_ajax(request, category_id):
    """حذف فئة عبر AJAX"""
    try:
        category = get_object_or_404(ProductCategory, id=category_id)
        
        # Check if category has subcategories
        if category.subcategories.exists():
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن حذف الفئة لأنها تحتوي على فئات فرعية'
            })
        
        # Check if category is used in products
        if category.finishedproduct_set.exists():
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن حذف الفئة لأنها مستخدمة في منتجات'
            })
        
        category_name = category.name
        category.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'تم حذف الفئة "{category_name}" بنجاح'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
@require_http_methods(["POST"])
def delete_size_group_ajax(request, size_group_id):
    """حذف مجموعة مقاسات عبر AJAX"""
    try:
        size_group = get_object_or_404(SizeGroup, id=size_group_id)
        
        # Check if size group is used in products
        if size_group.finishedproduct_set.exists():
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن حذف مجموعة المقاسات لأنها مستخدمة في منتجات'
            })
        
        size_group_name = size_group.name
        size_group.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'تم حذف مجموعة المقاسات "{size_group_name}" بنجاح'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
def get_category_ajax(request, category_id):
    """الحصول على بيانات فئة عبر AJAX"""
    try:
        category = get_object_or_404(ProductCategory, id=category_id)
        return JsonResponse({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'parent_id': category.parent.id if category.parent else None,
                'is_active': category.is_active,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
def get_size_group_ajax(request, size_group_id):
    """الحصول على بيانات مجموعة مقاسات عبر AJAX"""
    try:
        size_group = get_object_or_404(SizeGroup, id=size_group_id)
        return JsonResponse({
            'success': True,
            'size_group': {
                'id': size_group.id,
                'name': size_group.name,
                'sizes': size_group.sizes,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
def toggle_category_status_ajax(request, category_id):
    """تغيير حالة الفئة عبر AJAX"""
    try:
        category = get_object_or_404(ProductCategory, id=category_id)
        category.is_active = not category.is_active
        category.save()
        
        return JsonResponse({
            'success': True,
            'message': f'تم {"تفعيل" if category.is_active else "إلغاء تفعيل"} الفئة بنجاح',
            'is_active': category.is_active
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })

@login_required
def export_categories(request):
    """تصدير الفئات إلى CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="categories_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Add BOM for proper UTF-8 encoding in Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'ID',
        'اسم الفئة',
        'الفئة الأساسية',
        'الحالة',
        'عدد المنتجات',
        'عدد الفئات الفرعية',
        'تاريخ الإنشاء'
    ])
    
    # Get all categories
    categories = ProductCategory.objects.all().order_by('name')
    
    for category in categories:
        writer.writerow([
            category.id,
            category.name,
            category.parent.name if category.parent else 'فئة رئيسية',
            'نشط' if category.is_active else 'غير نشط',
            category.finishedproduct_set.count(),
            category.subcategories.count(),
            category.id  # Using ID as creation date since it's not in the model
        ])
    
    return response

@login_required
def export_size_groups(request):
    """تصدير مجموعات المقاسات إلى CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="size_groups_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Add BOM for proper UTF-8 encoding in Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'ID',
        'اسم المجموعة',
        'المقاسات',
        'عدد المقاسات',
        'عدد المنتجات',
        'تاريخ الإنشاء'
    ])
    
    # Get all size groups
    size_groups = SizeGroup.objects.all().order_by('name')
    
    for size_group in size_groups:
        writer.writerow([
            size_group.id,
            size_group.name,
            ', '.join(size_group.sizes) if size_group.sizes else '',
            len(size_group.sizes) if size_group.sizes else 0,
            size_group.finishedproduct_set.count(),
            size_group.id  # Using ID as creation date since it's not in the model
        ])
    
    return response