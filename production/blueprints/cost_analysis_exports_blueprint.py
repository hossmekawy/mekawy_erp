import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.conf import settings
from django.urls import path
from django.contrib.auth.decorators import login_required
import pdfkit
from decimal import Decimal
import logging

# --- CORRECTED IMPORTS ---
# FinalProduct has been removed and ProductBatch, Product have been added.
from ..models import (
    ProductionCostAnalysis, AssemblyComponent, FinishingComponent, 
    BOMItem, DyeingProcess
)
from warehouses.models import Product, ProductBatch

def get_full_context(analysis_id):
    """
    Helper function to gather all data for the reports.
    This function is now updated to use the new integrated models.
    """
    analysis = get_object_or_404(
        ProductionCostAnalysis.objects.select_related(
            'production_order__product__size_group',
            # --- FIX: Correct path to the fabric product ---
            'production_order__textile_stock__product', 
            'production_order__bom_version',
            'production_order__cutting_process',
        ), 
        pk=analysis_id
    )
    order = analysis.production_order
    bom = order.bom_version
    cutting_process = getattr(order, 'cutting_process', None)

    # --- Process Timeline & Durations (Logic is correct) ---
    timeline = []
    if cutting_process and cutting_process.cutting_date and cutting_process.completed_at:
        duration = cutting_process.completed_at - cutting_process.cutting_date
        timeline.append({
            'stage': 'القص', 
            'start': cutting_process.cutting_date, 
            'end': cutting_process.completed_at, 
            'duration': duration,
            'handler': cutting_process.cutter.get_full_name() if cutting_process.cutter else 'داخلي',
            'cost_per_piece': None
        })

    for assembly in order.assembly_processes.all():
        duration = (assembly.actual_completion_date - assembly.start_date) if assembly.start_date and assembly.actual_completion_date else None
        handler = assembly.external_manufacturer.name if assembly.assembly_type == 'outsourced' and assembly.external_manufacturer else (assembly.assembler.get_full_name() if assembly.assembler else 'داخلي')
        cost_per_piece = assembly.external_manufacturer.price_per_piece if assembly.assembly_type == 'outsourced' and assembly.external_manufacturer else None
        timeline.append({
            'stage': f'التجميع ({assembly.get_assembly_type_display()})', 
            'start': assembly.start_date, 
            'end': assembly.actual_completion_date, 
            'duration': duration,
            'handler': handler,
            'cost_per_piece': cost_per_piece
        })

        for dyeing in assembly.dyeing_processes.all():
            duration = (dyeing.actual_return_date - dyeing.sent_date) if dyeing.sent_date and dyeing.actual_return_date else None
            handler = dyeing.dyeing_facility.name if dyeing.dyeing_facility else 'غير محدد'
            cost_per_piece = dyeing.dyeing_cost_per_piece
            timeline.append({
                'stage': f'الصباغة ({dyeing.color_specification})', 
                'start': dyeing.sent_date, 
                'end': dyeing.actual_return_date, 
                'duration': duration,
                'handler': handler,
                'cost_per_piece': cost_per_piece
            })
            if finishing_process := getattr(dyeing, 'finishing_process', None):
                duration = (finishing_process.actual_completion_date - finishing_process.start_date) if finishing_process.start_date and finishing_process.actual_completion_date else None
                handler = finishing_process.external_manufacturer.name if finishing_process.finishing_type == 'outsourced' and finishing_process.external_manufacturer else (finishing_process.finisher.get_full_name() if finishing_process.finisher else 'داخلي')
                cost_per_piece = finishing_process.external_manufacturer.price_per_piece if finishing_process.finishing_type == 'outsourced' and finishing_process.external_manufacturer else None
                timeline.append({
                    'stage': 'التشطيب', 
                    'start': finishing_process.start_date, 
                    'end': finishing_process.actual_completion_date, 
                    'duration': duration,
                    'handler': handler,
                    'cost_per_piece': cost_per_piece
                })

    # --- BOM vs Actual Usage (Logic is correct) ---
    bom_comparison = []
    if bom:
        bom_materials = {item.material_id: item for item in bom.items.all()}
        actual_assembly = {c.material_id: c.quantity_sent for c in AssemblyComponent.objects.filter(assembly_process__production_order=order)}
        actual_finishing = {c.material_id: c.quantity_sent for c in FinishingComponent.objects.filter(finishing_process__dyeing_process__assembly_process__production_order=order)}
        actual_materials = actual_assembly
        for mat_id, qty in actual_finishing.items():
            actual_materials[mat_id] = actual_materials.get(mat_id, 0) + qty
        all_material_ids = set(bom_materials.keys()) | set(actual_materials.keys())
        for mat_id in all_material_ids:
            bom_item = bom_materials.get(mat_id)
            actual_qty = actual_materials.get(mat_id, Decimal('0.0'))
            material_obj = bom_item.material if bom_item else Product.objects.get(id=mat_id)
            bom_qty_per_piece = bom_item.quantity if bom_item else Decimal('0.0')
            bom_total_qty = bom_qty_per_piece * order.quantity_ordered
            bom_comparison.append({
                'material': material_obj.name,
                'bom_quantity': bom_total_qty,
                'actual_quantity': actual_qty,
                'variance': actual_qty - bom_total_qty
            })
            
    # --- Batch Data dictionary (REWRITTEN) ---
    batch_data = {
        'order': order,
        'cutting_process': cutting_process,
        'colors': list(set(DyeingProcess.objects.filter(assembly_process__production_order=order).values_list('color_specification', flat=True)))
    }
    
    # --- FIX: Query ProductBatch instead of FinalProduct ---
    batch_data['storage_locations'] = list(set(ProductBatch.objects.filter(
        stock__product=order.product,
        batch_number=order.batch_number
    ).values_list('stock__warehouse__name', flat=True)))
    
    fabric_bom_quantity = None
    if bom and order.textile_stock:
        try:
            # --- FIX: Correctly get the fabric product from the stock item ---
            fabric_material = order.textile_stock.product
            fabric_bom_item = BOMItem.objects.get(bom=bom, material=fabric_material)
            fabric_bom_quantity = fabric_bom_item.quantity
        except BOMItem.DoesNotExist:
            fabric_bom_quantity = None
            
    batch_data['fabric_bom_quantity'] = fabric_bom_quantity
    batch_data['fabric_cutting_quantity'] = cutting_process.single_layer_meterage if cutting_process else None

    return {
        'analysis': analysis,
        'order': order,
        'timeline': timeline,
        'bom_comparison': bom_comparison,
        'batch_data': batch_data,
    }

@login_required
def export_cost_analysis_pdf(request, pk):
    context = get_full_context(pk)
    html_string = render_to_string('pdf/production/cost_analysis_report.html', context)
    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8", 'page-size': 'A4', 'margin-top': '0.5in',
            'margin-right': '0.5in', 'margin-bottom': '0.5in', 'margin-left': '0.5in',
        })
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="CostAnalysis_{context["order"].order_number}.pdf"'
        return response
    except Exception as e:
        logging.error(f"PDF Generation Error: {e}")
        return HttpResponse(f"Error generating PDF: {e}", status=500)

@login_required
def export_cost_analysis_excel(request, pk):
    context = get_full_context(pk)
    analysis = context['analysis']
    order = context['order']
    wb = openpyxl.Workbook()
    
    ws = wb.active
    ws.title = "ملخص التقرير"
    ws.sheet_view.rightToLeft = True
    
    ws.append(['تقرير تحليل التكلفة لأمر الإنتاج', order.order_number])
    ws.append(['المنتج', order.product.name])
    ws.append(['الكمية', order.quantity_ordered])
    ws.append([])
    ws.append(['البند', 'التكلفة (جنيه)', 'النسبة المئوية'])
    ws.append(['إجمالي تكلفة المواد', analysis.total_material_cost, f"{analysis.material_cost_percentage:.2f}%"])
    ws.append(['إجمالي تكلفة العمليات', analysis.total_process_cost, f"{analysis.process_cost_percentage:.2f}%"])
    ws.append(['إجمالي التكاليف الإضافية', analysis.total_additional_cost, f"{(analysis.total_additional_cost / analysis.total_production_cost * 100) if analysis.total_production_cost else 0:.2f}%"])
    ws.append(['إجمالي تكلفة الإنتاج', analysis.total_production_cost, '100.00%'])
    ws.append(['تكلفة القطعة الواحدة', analysis.cost_per_piece, ''])

    ws2 = wb.create_sheet(title="الجدول الزمني للعمليات")
    ws2.sheet_view.rightToLeft = True
    ws2.append(['المرحلة', 'الجهة المنفذة', 'تكلفة القطعة', 'تاريخ البدء', 'تاريخ الانتهاء', 'المدة (أيام)'])
    for item in context['timeline']:
        duration_days = (item['duration'].days + item['duration'].seconds / 86400) if item['duration'] else ''
        ws2.append([
            item['stage'], 
            item.get('handler', ''),
            item.get('cost_per_piece', ''),
            item['start'].strftime('%Y-%m-%d %H:%M') if item['start'] else '', 
            item['end'].strftime('%Y-%m-%d %H:%M') if item['end'] else '', 
            f"{duration_days:.2f}" if isinstance(duration_days, float) else ''
        ])

    ws3 = wb.create_sheet(title="مقارنة استهلاك الخامات")
    ws3.sheet_view.rightToLeft = True
    ws3.append(['المادة الخام', 'الكمية حسب BOM', 'الكمية الفعلية المستخدمة', 'الفرق'])
    for item in context['bom_comparison']:
        ws3.append([item['material'], item['bom_quantity'], item['actual_quantity'], item['variance']])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="CostAnalysis_{order.order_number}.xlsx"'
    wb.save(response)
    return response

urlpatterns = [
    path('pdf/', export_cost_analysis_pdf, name='pdf'),
    path('excel/', export_cost_analysis_excel, name='excel'),
]
