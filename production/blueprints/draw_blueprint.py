from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponse

# PDF Generation Imports
import pdfkit
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

# App-specific imports
from ..models import GarmentDraw, BillOfMaterials
from ..forms import GarmentDrawForm, DrawPieceFormSet

class GarmentDrawListView(LoginRequiredMixin, ListView):
    model = GarmentDraw
    template_name = 'production/draw/draw_list.html'
    context_object_name = 'draws'
    paginate_by = 20

    def get_queryset(self):
        return GarmentDraw.objects.select_related('bom__product', 'created_by').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_boms'] = BillOfMaterials.objects.filter(is_active=True).select_related('product').order_by('product__name', '-version')
        return context

class GarmentDrawDetailView(LoginRequiredMixin, DetailView):
    model = GarmentDraw
    template_name = 'production/draw/draw_detail.html'
    context_object_name = 'draw'

    def get_queryset(self):
        return GarmentDraw.objects.select_related('bom__product', 'bom__size_group', 'created_by').prefetch_related('pieces')

class GarmentDrawCreateView(LoginRequiredMixin, CreateView):
    model = GarmentDraw
    form_class = GarmentDrawForm
    template_name = 'production/draw/draw_form.html'

    def get_initial(self):
        initial = super().get_initial()
        bom_id = self.request.GET.get('bom_id')
        if bom_id:
            try:
                initial['bom'] = BillOfMaterials.objects.get(pk=bom_id)
            except BillOfMaterials.DoesNotExist:
                pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = DrawPieceFormSet(self.request.POST, prefix='pieces')
        else:
            context['formset'] = DrawPieceFormSet(prefix='pieces')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        with transaction.atomic():
            if formset.is_valid():
                form.instance.created_by = self.request.user
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                messages.success(self.request, 'تم إنشاء رسمة القص بنجاح.')
                return redirect(self.object.get_absolute_url())
            else:
                messages.error(self.request, "الرجاء تصحيح الأخطاء في قائمة القطع.")
                return self.form_invalid(form)

class GarmentDrawUpdateView(LoginRequiredMixin, UpdateView):
    model = GarmentDraw
    form_class = GarmentDrawForm
    template_name = 'production/draw/draw_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = DrawPieceFormSet(self.request.POST, instance=self.object, prefix='pieces')
        else:
            context['formset'] = DrawPieceFormSet(instance=self.object, prefix='pieces')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        with transaction.atomic():
            if formset.is_valid():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                messages.success(self.request, 'تم تحديث رسمة القص بنجاح.')
                return redirect(self.object.get_absolute_url())
            else:
                messages.error(self.request, "الرجاء تصحيح الأخطاء في قائمة القطع.")
                return self.form_invalid(form)

class GarmentDrawDeleteView(LoginRequiredMixin, DeleteView):
    model = GarmentDraw
    template_name = 'production/draw/draw_confirm_delete.html'
    success_url = reverse_lazy('production:draws:draw_list')

    def form_valid(self, form):
        messages.success(self.request, f"تم حذف رسمة القص '{self.object}' بنجاح.")
        return super().form_valid(form)

# AJAX view to get sizes for a BOM
def get_sizes_for_bom_ajax(request):
    bom_id = request.GET.get('bom_id')
    sizes = []
    if bom_id:
        try:
            bom = get_object_or_404(BillOfMaterials.objects.select_related('size_group'), id=bom_id)
            if bom.size_group:
                sizes = bom.size_group.sizes
        except BillOfMaterials.DoesNotExist:
            pass
    return JsonResponse({'sizes': sizes})
def get_draws_for_bom_ajax(request):
    bom_id = request.GET.get('bom_id')
    draws_dict = {}
    if bom_id:
        try:
            draws = GarmentDraw.objects.filter(bom_id=bom_id)
            for draw in draws:
                draws_dict[draw.size] = draw.id
        except Exception:
            pass
    return JsonResponse({'draws': draws_dict})

# PDF Print Views
def print_draw_pdf(request, pk):
    draw = get_object_or_404(GarmentDraw, pk=pk)
    context = {
        'draw': draw,
        'timestamp': timezone.now()
    }
    
    html_string = render_to_string('pdf/production/draw_pdf.html', context)

    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8", 'page-size': 'A4', 'margin-top': '0.75in',
            'margin-right': '0.75in', 'margin-bottom': '0.75in', 'margin-left': '0.75in',
        })

        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Draw_{draw.bom.product.code}_{draw.size}_{draw.id}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect(draw.get_absolute_url())

def bulk_print_draw_pdf(request):
    if request.method != 'POST':
        messages.error(request, "طلب غير صالح.")
        return redirect('production:draws:draw_list')

    draw_ids_str = request.POST.get('selected_draw_ids', '')
    if not draw_ids_str:
        messages.warning(request, "لم يتم اختيار أي رسومات للطباعة.")
        return redirect('production:draws:draw_list')
        
    draw_ids = [int(id) for id in draw_ids_str.split(',') if id.isdigit()]
    
    # --- FIX FOR DUPLICATE PRINTING ---
    # 1. Fetch only the unique draws required from the database to be efficient.
    unique_draw_ids = set(draw_ids)
    draw_objects = GarmentDraw.objects.filter(
        pk__in=unique_draw_ids
    ).select_related('bom__product', 'created_by').prefetch_related('pieces')

    # 2. Create a dictionary for quick lookups.
    draw_map = {draw.id: draw for draw in draw_objects}
    
    # 3. Build the final list for the template, respecting the user's exact order and duplicates.
    draws_for_template = [draw_map.get(id) for id in draw_ids if id in draw_map]
    # --- END OF FIX ---

    if not draws_for_template:
        messages.error(request, "لم يتم العثور على الرسومات المحددة.")
        return redirect('production:draws:draw_list')

    context = {
        'draws': draws_for_template,
        'timestamp': timezone.now(),
        'bom': draws_for_template[0].bom, # Use the first item for header info
    }
    
    html_string = render_to_string('pdf/production/bulk_draw_pdf.html', context)

    try:
        pdf_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
        pdf = pdfkit.from_string(html_string, False, configuration=pdf_config, options={
            'encoding': "UTF-8", 'page-size': 'A4', 'margin-top': '0.75in',
            'margin-right': '0.75in', 'margin-bottom': '0.75in', 'margin-left': '0.75in',
        })

        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"BulkDraws_{draws_for_template[0].bom.product.code}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ملف PDF: {e}")
        return redirect('production:draws:draw_list')
