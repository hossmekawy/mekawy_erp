from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import threading
import base64
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
import pdfkit
from django.template.loader import render_to_string
from django.conf import settings
from django.core.files.storage import default_storage
from hr.forms import DepartmentForm, EmployeeForm

from .models import Employee, Attendance
from django.utils import timezone
import calendar
from datetime import date, time, timedelta, datetime
from django.core.management import call_command
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q # <--- ADD THIS IMPORT
from zk import ZK, const
from zk.user import User as ZKUser

# --- ZKTeco Device Connection Settings ---
DEVICE_IP = '192.168.1.52'
DEVICE_PORT = 4370
DEVICE_PASSWORD = 0

def connect_to_device(timeout=10):
    """Helper function to connect to the ZKTeco device with a specific timeout."""
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=timeout, password=DEVICE_PASSWORD, force_udp=False, ommit_ping=False)
    try:
        conn = zk.connect()
        return conn
    except Exception as e:
        print(f"Device connection failed: {e}")
        return None
    
def _enroll_finger_in_background(employee_id_str):
    """
    This function runs in a separate thread to avoid blocking the web request.
    It connects to the device and puts it in enrollment mode.
    """
    print(f"BACKGROUND TASK: Starting enrollment for user_id: {employee_id_str}")
    conn = None
    try:
        # Use a longer timeout for the background task as the device might be busy.
        # The device itself has a ~60s timeout. This connection timeout must be longer.
        zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=65, password=DEVICE_PASSWORD, force_udp=False, ommit_ping=False)
        conn = zk.connect()
        if conn:
            print("BACKGROUND TASK: Connected to device.")
            # This command tells the device to start listening. The device itself will
            # wait for a finger for its own timeout period. The pyzk library call
            # will block here, but it's safe because it's in a background thread.
            conn.enroll_user(user_id=employee_id_str)
            print(f"BACKGROUND TASK: Enrollment process finished or timed out on device for user_id: {employee_id_str}.")
    except Exception as e:
        print(f"BACKGROUND TASK ERROR for user_id {employee_id_str}: {e}")
    finally:
        if conn and conn.is_connect:
            print(f"BACKGROUND TASK: Disconnecting for user_id: {employee_id_str}")
            conn.disconnect()

@staff_member_required
def employee_create(request):
    """
    Handles the creation of a new employee and adds them to the ZKTeco device.
    """
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            employee = form.save()
            messages.success(request, 'تمت إضافة الموظف بنجاح في النظام.')

            conn = connect_to_device()
            if conn:
                try:
                    conn.disable_device()
                    device_users = conn.get_users()
                    existing_uids = [u.uid for u in device_users]
                    new_uid = max(existing_uids) + 1 if existing_uids else 1
                    
                    conn.set_user(uid=new_uid, name=employee.full_name, user_id=str(employee.employee_id))
                    messages.success(request, f'تمت إضافة الموظف "{employee.full_name}" إلى جهاز البصمة بنجاح.')
                except Exception as e:
                    messages.error(request, f'فشل في إضافة الموظف لجهاز البصمة: {e}')
                finally:
                    conn.enable_device()
                    conn.disconnect()
            else:
                messages.error(request, 'فشل الاتصال بجهاز البصمة. تم حفظ الموظف في النظام فقط.')

            return redirect('hr:employee_list')
    else:
        form = EmployeeForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة موظف جديد',
        'button_text': 'إضافة'
    }
    return render(request, 'hr/employee_form.html', context)

@staff_member_required
def enroll_fingerprint(request, employee_id):
    """
    Starts the fingerprint enrollment process in a background thread
    and returns an immediate response to the user.
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission Denied'}, status=403)

    employee = get_object_or_404(Employee, id=employee_id)
    
    # Start the enrollment process in a background thread
    enroll_thread = threading.Thread(
        target=_enroll_finger_in_background,
        args=(str(employee.employee_id),)
    )
    enroll_thread.daemon = True  # Allows the main app to exit even if threads are running
    enroll_thread.start()

    # Return an immediate response to the user
    message = f"تم إرسال أمر تفعيل تسجيل البصمة للموظف: {employee.full_name}."
    return JsonResponse({
        'status': 'success',
        'message': message,
        'employee_name': employee.full_name
    })

def employee_list(request):
    """
    Displays a paginated list of all active employees, with search functionality.
    """
    search_query = request.GET.get('q', '')
    
    # Start with the base queryset, ordered for consistent pagination
    employee_queryset = Employee.objects.filter(is_active=True).order_by('full_name')

    if search_query:
        employee_queryset = employee_queryset.filter(
            Q(full_name__icontains=search_query) |
            Q(employee_id__icontains=search_query)
        )

    # --- Pagination Logic ---
    paginator = Paginator(employee_queryset, 15) # Show 15 employees per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    # --- End Pagination Logic ---

    context = {
        'employees': page_obj,  # Pass the page object to the template
        'page_title': 'قائمة الموظفين',
        'search_query': search_query,
    }
    return render(request, 'hr/employee_list.html', context)

@staff_member_required
def employee_bulk_delete(request):
    """
    Handles the bulk deletion of selected employees.
    """
    if not (request.user.is_superuser or request.user.role in ['admin', 'manager']):
        raise PermissionDenied

    if request.method == 'POST':
        employee_ids = request.POST.getlist('employee_ids')
        if employee_ids:
            employees_to_delete = Employee.objects.filter(id__in=employee_ids)
            count = employees_to_delete.count()
            employees_to_delete.delete()
            messages.success(request, f'تم حذف {count} موظف بنجاح.')
        else:
            messages.warning(request, 'لم يتم تحديد أي موظفين للحذف.')
    return redirect('hr:employee_list')

@staff_member_required
def employee_detail(request, employee_id):
    """
    Displays all data for a single employee, including today's attendance status.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    
    # Get today's attendance status
    today_attendance = None
    try:
        # Use timezone.localdate() to be sure about the date
        today_attendance = Attendance.objects.get(employee=employee, date=timezone.localdate())
    except Attendance.DoesNotExist:
        pass  # today_attendance remains None

    context = {
        'employee': employee,
        'page_title': f'تفاصيل الموظف: {employee.full_name}',
        'today_attendance': today_attendance,
    }
    return render(request, 'hr/employee_detail.html', context)

@staff_member_required
def print_employee_id_card(request, employee_id):
    """
    Generates a PDF ID card for a specific employee using wkhtmltopdf.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    
    photo_data_uri = ''
    if employee.photo and default_storage.exists(employee.photo.name):
        try:
            with default_storage.open(employee.photo.name, 'rb') as image_file:
                image_data = image_file.read()
                base64_data = base64.b64encode(image_data).decode('utf-8')
                # A more robust solution could use a library like python-magic to find the mime type
                photo_data_uri = f'data:image/jpeg;base64,{base64_data}'
        except Exception as e:
            print(f"Could not process image for PDF: {e}")

    context = {
        'employee': employee,
        'photo_data_uri': photo_data_uri,
    }

    try:
        # Render the HTML template with employee data
        html_string = render_to_string('pdf/hr/employee_id_card.html', context)
        
        # Get path to wkhtmltopdf executable from settings
        path_wkhtmltopdf = settings.WKHTMLTOPDF_PATH
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
        
        # Define PDF options for custom size (2.63 x 3.88 inches) and no margins
        options = {
            'page-width': '66.8mm',
            'page-height': '98.6mm',
            'margin-top': '0mm',
            'margin-right': '0mm',
            'margin-bottom': '0mm',
            'margin-left': '0mm',
            'encoding': "UTF-8",
            'enable-local-file-access': None, # Helps with finding local assets if needed
        }
        
        # Generate PDF from the HTML string
        pdf_file = pdfkit.from_string(html_string, False, configuration=config, options=options)
        
        # Create the HTTP response with the PDF file
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="ID_Card_{employee.employee_id}.pdf"'
        
        return response
    except Exception as e:
        # Handle potential errors, e.g., wkhtmltopdf not found or rendering issues
        print(f"Error generating PDF ID card: {e}")
        return HttpResponse(f"Error generating PDF: {e}", status=500)


@staff_member_required
def employee_update(request, employee_id):
    """Handles the updating of an existing employee."""
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات الموظف بنجاح.')
            return redirect('hr:employee_list')
    else:
        form = EmployeeForm(instance=employee)
        
    context = {
        'form': form,
        'employee': employee,
        'page_title': f'تعديل بيانات: {employee.full_name}',
        'form_title': f'تعديل بيانات: {employee.full_name}',
        'button_text': 'حفظ التعديلات'
    }
    return render(request, 'hr/employee_form.html', context)

@staff_member_required
def employee_delete(request, employee_id):
    """Handles the deletion of an existing employee."""
    if not (request.user.is_superuser or request.user.role in ['admin', 'manager']):
        raise PermissionDenied

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        employee_name = employee.full_name
        employee.delete()
        messages.success(request, f'تم حذف الموظف {employee_name} بنجاح.')
        return redirect('hr:employee_list')
    
    context = {
        'employee': employee,
        'page_title': f'تأكيد حذف: {employee.full_name}'
    }
    return render(request, 'hr/employee_confirm_delete.html', context)


@staff_member_required
def department_create(request):
    """Handles creating a department via AJAX from a modal."""
    if not (request.user.is_superuser or request.user.role in ['admin', 'manager']):
        return JsonResponse({'status': 'error', 'message': 'Permission Denied'}, status=403)

    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            return JsonResponse({
                'status': 'success',
                'message': 'تم إنشاء القسم بنجاح.',
                'department': {
                    'id': department.id,
                    'name': department.name
                }
            })
        else:
            # Prepare error messages for JSON response
            errors = {field: error[0] for field, error in form.errors.items()}
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def process_day_data(day_date, record, employee):
    """
    Helper function to process attendance data for a single day.
    This version correctly handles timezones for display.
    """
    day_name = calendar.day_name[day_date.weekday()]
    arabic_day_names = {
        'Saturday': 'السبت', 'Sunday': 'الأحد', 'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس', 'Friday': 'الجمعة'
    }
    day_name_ar = arabic_day_names.get(day_name, day_name)
    
    day_info = {
        'date': day_date,
        'day_name': day_name_ar,
        'check_in': None,
        'check_out': None,
        'status': 'غائب' # Default status
    }

    if record:
        has_in = bool(record.check_in)
        has_out = bool(record.check_out)

        local_check_in_time = None
        if has_in:
            # Convert stored UTC time to local time before extracting the time part
            local_check_in = timezone.localtime(record.check_in)
            local_check_in_time = local_check_in.time()
            day_info['check_in'] = local_check_in_time

        local_check_out_time = None
        if has_out:
            # Convert stored UTC time to local time
            local_check_out = timezone.localtime(record.check_out)
            local_check_out_time = local_check_out.time()
            day_info['check_out'] = local_check_out_time

        # Determine status with clearer logic
        if has_in and has_out:
            if local_check_in_time > employee.work_start_time:
                day_info['status'] = 'حضور متأخر'
            elif local_check_out_time < employee.work_end_time:
                day_info['status'] = 'انصراف مبكر'
            else:
                day_info['status'] = 'حاضر'
        elif has_in or has_out:
            day_info['status'] = 'بصمة ناقصة'
        # If neither, status remains 'غائب'

    # Check for weekends (Friday in this case)
    if day_date.weekday() == 4:
        day_info['status'] = 'عطلة'
        
    return day_info
@staff_member_required
def employee_attendance_detail(request, employee_id):
    """
    Displays a detailed attendance report, switchable between weekly and monthly views.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    view_type = request.GET.get('view', 'month')  # Default to monthly view

    report_data = []
    context = {
        'employee': employee,
        'page_title': f'تقرير حضور وانصراف - {employee.full_name}',
        'view_type': view_type,
    }

    if view_type == 'week':
        # --- WEEKLY LOGIC ---
        try:
            selected_date_str = request.GET.get('date')
            selected_date = date.fromisoformat(selected_date_str)
        except (ValueError, TypeError):
            selected_date = timezone.now().date()

        days_since_saturday = (selected_date.weekday() + 2) % 7
        start_of_week = selected_date - timedelta(days=days_since_saturday)
        end_of_week = start_of_week + timedelta(days=5)
        
        week_dates = [start_of_week + timedelta(days=i) for i in range(6)]
        
        attendance_records = Attendance.objects.filter(
            employee=employee,
            date__range=[start_of_week, end_of_week]
        ).order_by('date')
        
        attendance_dict = {record.date: record for record in attendance_records}
        
        for day_date in week_dates:
            record = attendance_dict.get(day_date)
            report_data.append(process_day_data(day_date, record, employee))

        context.update({
            'week_start_date': start_of_week,
            'week_end_date': end_of_week,
            'prev_week_date': start_of_week - timedelta(days=7),
            'next_week_date': start_of_week + timedelta(days=7),
        })

    else:  # Default to 'month'
        # --- MONTHLY LOGIC ---
        try:
            year = int(request.GET.get('year', timezone.now().year))
            month = int(request.GET.get('month', timezone.now().month))
        except (ValueError, TypeError):
            year = timezone.now().year
            month = timezone.now().month

        num_days = calendar.monthrange(year, month)[1]
        month_dates = [date(year, month, day) for day in range(1, num_days + 1)]
        
        attendance_records = Attendance.objects.filter(
            employee=employee,
            date__year=year,
            date__month=month
        ).order_by('date')
        
        attendance_dict = {record.date: record for record in attendance_records}
        
        for day_date in month_dates:
            record = attendance_dict.get(day_date)
            report_data.append(process_day_data(day_date, record, employee))

        current_date = date(year, month, 1)
        prev_month_date = current_date - timedelta(days=1)
        next_month_date = current_date + timedelta(days=num_days)

        context.update({
            'current_month_name': calendar.month_name[month],
            'current_year': year,
            'prev_year': prev_month_date.year,
            'prev_month': prev_month_date.month,
            'next_year': next_month_date.year,
            'next_month': next_month_date.month,
        })

    context['report_data'] = report_data
    return render(request, 'hr/employee_attendance_detail.html', context)



@staff_member_required
def weekly_attendance_report(request):
    """
    Displays a weekly attendance grid with summaries and handles PDF export.
    """
    try:
        selected_date_str = request.GET.get('date')
        selected_date = date.fromisoformat(selected_date_str)
    except (ValueError, TypeError):
        selected_date = timezone.now().date()

    days_since_saturday = (selected_date.weekday() + 2) % 7
    start_of_week = selected_date - timedelta(days=days_since_saturday)
    end_of_week = start_of_week + timedelta(days=6)

    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
    work_days_in_week = sum(1 for d in week_dates if d.weekday() != 4) # Count days that are not Friday

    attendance_records = Attendance.objects.filter(
        date__range=[start_of_week, end_of_week]
    ).select_related('employee').order_by('employee__full_name', 'date')

    # Group records by employee for initial processing
    initial_report_data = defaultdict(lambda: {d: None for d in week_dates})
    for record in attendance_records:
        initial_report_data[record.employee][record.date] = record

    # --- New logic to process data with summaries ---
    processed_report_data = {}
    LATE_THRESHOLD = time(8, 10)
    HALF_DAY_THRESHOLD = time(8, 30)

    for employee, daily_records_map in initial_report_data.items():
        summary = {
            'attended_days': 0, 'total_lateness': timedelta(0),
            'late_days': 0, 'half_days': 0, 'absent_days': 0,
        }
        processed_daily_records = {}

        for day_date, record in daily_records_map.items():
            is_workday = day_date.weekday() != 4  # Friday is a holiday

            day_info = {'record': record, 'status': 'غائب', 'css_class': 'status-absent'}

            if record and record.check_in:
                summary['attended_days'] += 1
                check_in_time = timezone.localtime(record.check_in).time()
                
                day_info['status'] = 'حاضر'
                day_info['css_class'] = 'status-present'

                if check_in_time > employee.work_start_time:
                    start_dt = timezone.make_aware(datetime.combine(day_date, employee.work_start_time))
                    check_in_dt = timezone.localtime(record.check_in)
                    lateness_delta = check_in_dt - start_dt
                    if lateness_delta.total_seconds() > 0:
                        summary['total_lateness'] += lateness_delta

                if check_in_time > HALF_DAY_THRESHOLD:
                    day_info['status'] = 'نصف يوم'
                    day_info['css_class'] = 'status-half-day'
                    summary['half_days'] += 1
                elif check_in_time > LATE_THRESHOLD:
                    day_info['status'] = 'تأخير'
                    day_info['css_class'] = 'status-late-warning'
                    summary['late_days'] += 1

            elif is_workday:
                summary['absent_days'] += 1
            elif not is_workday:
                day_info['status'] = 'عطلة'
                day_info['css_class'] = 'status-weekend'

            processed_daily_records[day_date] = day_info

        total_seconds = summary['total_lateness'].total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        if hours > 0:
            summary['lateness_str'] = f"{hours} س و {minutes} د"
        else:
            summary['lateness_str'] = f"{minutes} دقيقة"

        processed_report_data[employee] = {
            'daily_records': processed_daily_records,
            'summary': summary
        }

    context = {
        'page_title': 'تقرير الحضور والغياب الأسبوعي',
        'week_dates': week_dates,
        'report_data': processed_report_data,
        'week_start_date': start_of_week,
        'week_end_date': end_of_week,
        'prev_week_date': start_of_week - timedelta(days=7),
        'next_week_date': start_of_week + timedelta(days=7),
        'work_days_in_week': work_days_in_week,
    }

    if request.GET.get('format') == 'pdf':
        try:
            path_wkhtmltopdf = settings.WKHTMLTOPDF_PATH
            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
            html_string = render_to_string('pdf/hr/weekly_attendance_report_pdf.html', context)
            options = {'page-size': 'A4', 'orientation': 'Landscape', 'encoding': "UTF-8", 'enable-local-file-access': None}
            pdf_file = pdfkit.from_string(html_string, False, configuration=config, options=options)
            response = HttpResponse(pdf_file, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="weekly_report_{start_of_week}.pdf"'
            return response
        except Exception as e:
            return HttpResponse(f"Error generating PDF: {e}", status=500)

    return render(request, 'hr/weekly_attendance_report.html', context)


@staff_member_required
def fetch_attendance_data(request):
    """
    A view that triggers the fetch_attendance management command.
    This is protected to ensure only staff members can run it.
    """
    if request.method == 'GET':
        try:
            # Use io.StringIO to capture the output of the management command
            out = io.StringIO()
            err = io.StringIO()
            
            # Execute the command and redirect its output
            with redirect_stdout(out), redirect_stderr(err):
                call_command('fetch_attendance')
            
            output = out.getvalue()
            error = err.getvalue()

            if error:
                # If the command wrote to stderr, report it as an error
                return JsonResponse({'status': 'error', 'message': error}, status=500)

            # If successful, return the command's standard output
            return JsonResponse({'status': 'success', 'message': output})

        except Exception as e:
            # Catch any other exceptions during the process
            return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method. Please use GET.'}, status=405)


@staff_member_required
def manual_attendance_view(request):
    """
    Displays a weekly grid for manually entering attendance for all employees.
    """
    try:
        selected_date_str = request.GET.get('date')
        selected_date = date.fromisoformat(selected_date_str)
    except (ValueError, TypeError):
        selected_date = timezone.now().date()

    days_since_saturday = (selected_date.weekday() + 2) % 7
    start_of_week = selected_date - timedelta(days=days_since_saturday)
    end_of_week = start_of_week + timedelta(days=5)
    
    week_dates = [start_of_week + timedelta(days=i) for i in range(6)]
    employees = Employee.objects.filter(is_active=True).order_by('full_name')
    
    attendance_records = Attendance.objects.filter(
        employee__in=employees,
        date__range=[start_of_week, end_of_week]
    ).select_related('employee')

    attendance_map = {emp.id: {} for emp in employees}
    for record in attendance_records:
        if record.employee_id in attendance_map:
            attendance_map[record.employee_id][record.date] = record

    grid_data = []
    for emp in employees:
        employee_row = {'employee': emp, 'days': []}
        for day_date in week_dates:
            record = attendance_map[emp.id].get(day_date)
            day_info = process_day_data(day_date, record, emp)
            employee_row['days'].append(day_info)
        grid_data.append(employee_row)

    context = {
        'page_title': 'تسجيل الحضور اليدوي',
        'week_dates': week_dates,
        'grid_data': grid_data,
        'week_start_date': start_of_week,
        'week_end_date': end_of_week,
        'prev_week_date': start_of_week - timedelta(days=7),
        'next_week_date': start_of_week + timedelta(days=7),
    }
    return render(request, 'hr/manual_attendance.html', context)

@staff_member_required
def update_manual_attendance(request):
    """
    Handles AJAX requests to update or create an attendance record.
    This version is timezone-aware.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        employee_id = int(data.get('employee_id'))
        record_date_str = data.get('date')
        check_in_str = data.get('check_in')
        check_out_str = data.get('check_out')

        employee = get_object_or_404(Employee, id=employee_id)
        record_date = date.fromisoformat(record_date_str)

        check_in_dt = None
        if check_in_str:
            check_in_time = time.fromisoformat(check_in_str)
            naive_dt = datetime.combine(record_date, check_in_time)
            # Make the datetime object aware of the project's timezone
            check_in_dt = timezone.make_aware(naive_dt)

        check_out_dt = None
        if check_out_str:
            check_out_time = time.fromisoformat(check_out_str)
            naive_dt = datetime.combine(record_date, check_out_time)
            # Make the datetime object aware of the project's timezone
            check_out_dt = timezone.make_aware(naive_dt)

        attendance_record, created = Attendance.objects.update_or_create(
            employee=employee,
            date=record_date,
            defaults={
                'check_in': check_in_dt,
                'check_out': check_out_dt
            }
        )
        
        day_info = process_day_data(record_date, attendance_record, employee)

        return JsonResponse({'status': 'success', 'message': 'تم الحفظ بنجاح', 'new_status': day_info['status']})

    except (json.JSONDecodeError, KeyError, ValueError, Employee.DoesNotExist) as e:
        return JsonResponse({'status': 'error', 'message': f'بيانات غير صالحة: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'حدث خطأ غير متوقع: {str(e)}'}, status=500)

@staff_member_required
def sync_employees_from_device(request):
    """
    A view that triggers the sync_employees management command.
    """
    if request.method == 'GET':
        try:
            out = io.StringIO()
            err = io.StringIO()
            
            with redirect_stdout(out), redirect_stderr(err):
                call_command('sync_employees')
            
            output = out.getvalue()
            error = err.getvalue()

            if error:
                return JsonResponse({'status': 'error', 'message': error}, status=500)
            return JsonResponse({'status': 'success', 'message': output})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
