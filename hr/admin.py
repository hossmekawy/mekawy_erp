from django.contrib import admin
from .models import Department, Employee, Attendance

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'employee_id', 'department', 'job_title', 'is_active')
    list_filter = ('department', 'is_active', 'gender')
    search_fields = ('full_name', 'employee_id', 'email', 'phone_number')
    list_per_page = 25

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'check_in', 'check_out', 'work_duration')
    list_filter = ('date', 'employee__department')
    search_fields = ('employee__full_name', 'employee__employee_id')
    date_hierarchy = 'date'
    list_per_page = 30
