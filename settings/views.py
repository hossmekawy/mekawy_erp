import os
import io
import shutil
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.http import HttpResponse
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
from .forms import GeneralSettingsForm, AppearanceSettingsForm, ImportBackupForm
from .models import Setting

@staff_member_required
def settings_view(request):
    """
    Handles displaying and updating all settings, separated by forms.
    """
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'general':
            form = GeneralSettingsForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'تم حفظ الإعدادات العامة بنجاح!')
                return redirect('settings:general')
        
        elif form_type == 'appearance':
            form = AppearanceSettingsForm(request.POST, request.FILES)
            if form.is_valid():
                # Handle the logo upload
                if 'site_logo' in request.FILES:
                    logo_file = request.FILES['site_logo']
                    try:
                        old_logo_setting = Setting.objects.get(key='site_logo')
                        old_logo_path = old_logo_setting.value.replace(django_settings.MEDIA_URL, '')
                        if default_storage.exists(old_logo_path):
                            default_storage.delete(old_logo_path)
                    except (Setting.DoesNotExist, ValueError):
                        pass
                    
                    file_name = default_storage.save(f"logos/{logo_file.name}", logo_file)
                    logo_url = default_storage.url(file_name)
                    
                    Setting.objects.update_or_create(key='site_logo', defaults={'value': logo_url})
                
                # Handle clearing the logo
                elif form.cleaned_data.get('site_logo') is False:
                    try:
                        old_logo_setting = Setting.objects.get(key='site_logo')
                        old_logo_path = old_logo_setting.value.replace(django_settings.MEDIA_URL, '')
                        if default_storage.exists(old_logo_path):
                            default_storage.delete(old_logo_path)
                        old_logo_setting.delete()
                    except (Setting.DoesNotExist, ValueError):
                        pass

                # Save other appearance settings (colors)
                form.save()
                messages.success(request, 'تم حفظ إعدادات المظهر بنجاح!')
                return redirect('settings:general')

    general_form = GeneralSettingsForm()
    appearance_form = AppearanceSettingsForm()
    import_form = ImportBackupForm()
    
    context = {
        'general_form': general_form,
        'appearance_form': appearance_form,
        'import_form': import_form,
        'page_title': 'الإعدادات'
    }
    return render(request, 'settings/settings.html', context)

@staff_member_required
def create_backup(request):
    """
    Creates a direct backup of the SQLite database file and serves it for download.
    """
    try:
        db_path = django_settings.DATABASES['default']['NAME']
        if 'sqlite3' not in django_settings.DATABASES['default']['ENGINE']:
            messages.error(request, 'هذه الميزة متاحة فقط لقواعد بيانات SQLite.')
            return redirect('settings:general')

        if not os.path.exists(db_path):
            messages.error(request, 'لم يتم العثور على ملف قاعدة البيانات.')
            return redirect('settings:general')

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        file_name = f'mekawy_erp_backup_{timestamp}.db'
        
        with open(db_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/x-sqlite3')
            response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        
        return response
            
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء إنشاء النسخة الاحتياطية: {e}')
        return redirect('settings:general')

@staff_member_required
def import_backup(request):
    """
    Imports data from an uploaded backup file (.json or .db).
    """
    if not request.user.is_superuser:
        messages.error(request, 'ليس لديك الصلاحية لتنفيذ هذا الإجراء!')
        return redirect('settings:general')

    if request.method == 'POST':
        form = ImportBackupForm(request.POST, request.FILES)
        if form.is_valid():
            backup_file = request.FILES['backup_file']
            file_name = backup_file.name

            if file_name.endswith('.db'):
                db_path = django_settings.DATABASES['default']['NAME']
                temp_db_path = f"{db_path}.upload"
                try:
                    with open(temp_db_path, 'wb+') as temp_file:
                        for chunk in backup_file.chunks():
                            temp_file.write(chunk)
                    shutil.move(temp_db_path, db_path)
                    messages.warning(request, 'تم استبدال ملف قاعدة البيانات بنجاح. يجب إعادة تشغيل الخادم فوراً.')
                except Exception as e:
                    messages.error(request, f'حدث خطأ فادح أثناء استبدال قاعدة البيانات: {e}.')
                    if os.path.exists(temp_db_path):
                        os.remove(temp_db_path)
            
            elif file_name.endswith('.json'):
                temp_file_path = os.path.join(django_settings.BASE_DIR, 'temp_backup.json')
                try:
                    with open(temp_file_path, 'wb+') as temp_file:
                        for chunk in backup_file.chunks():
                            temp_file.write(chunk)
                    call_command('loaddata', temp_file_path)
                    messages.success(request, 'تم استيراد البيانات من ملف JSON بنجاح!')
                except Exception as e:
                    messages.error(request, f'حدث خطأ أثناء استيراد النسخة الاحتياطية: {e}')
                finally:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            
            else:
                messages.error(request, 'نوع الملف غير مدعوم. يرجى تحميل ملف .json أو .db فقط.')

            return redirect('settings:general')
    
    return redirect('settings:general')
