from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    # URL for the list of all employees
    path('employees/', views.employee_list, name='employee_list'),

    # URL for the new weekly attendance report
    path('attendance/weekly-report/', views.weekly_attendance_report, name='weekly_attendance_report'),

    # URL for a single employee's details
    path('employee/<int:employee_id>/', views.employee_detail, name='employee_detail'),

    # URL for a single employee's attendance details
    path('employee/<int:employee_id>/attendance/', views.employee_attendance_detail, name='employee_attendance_detail'),

    # URL for printing an employee's ID card
    path('employee/<int:employee_id>/print-id/', views.print_employee_id_card, name='print_employee_id_card'),

    # URL to trigger the attendance fetch command
    path('fetch-attendance-data/', views.fetch_attendance_data, name='fetch_attendance_data'),
    
    # URLs for creating, updating, and deleting employees
    path('employee/add/', views.employee_create, name='employee_create'),
    path('employee/<int:employee_id>/update/', views.employee_update, name='employee_update'),
    path('employee/<int:employee_id>/delete/', views.employee_delete, name='employee_delete'),

    # URL for creating a department via modal
    path('department/add/', views.department_create, name='department_create'),

    # URLs for Manual Attendance
    path('attendance/manual/', views.manual_attendance_view, name='manual_attendance'),
    path('attendance/manual/update/', views.update_manual_attendance, name='update_manual_attendance'),

    # URL for syncing employees from ZKTeco device
    path('employees/sync/', views.sync_employees_from_device, name='sync_employees'),

    # URL for bulk deleting employees
    path('employees/bulk-delete/', views.employee_bulk_delete, name='employee_bulk_delete'),
    
    # URL to trigger fingerprint enrollment on the device
    path('employee/<int:employee_id>/enroll-fingerprint/', views.enroll_fingerprint, name='employee_enroll_fingerprint'),
]
