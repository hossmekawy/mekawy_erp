from django import forms
from .models import Employee, Department

class DepartmentForm(forms.ModelForm):
    """Form for creating a new Department."""
    class Meta:
        model = Department
        fields = ['name']
        labels = {
            'name': 'اسم القسم الجديد'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'})
        }

class EmployeeForm(forms.ModelForm):
    """Form for creating and updating Employee instances."""
    
    class Meta:
        model = Employee
        fields = [
            'full_name', 'employee_id', 'department', 'job_title', 
            'phone_number', 'email', 'address', 'gender', 
            'birth_date', 'hire_date', 'salary', 'work_start_time', 
            'work_end_time', 'photo', 'id_face_image', 'id_back_image', 'is_active'
        ]
        # Use HTML5 widgets for a better user experience
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
            'work_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'email': forms.EmailInput(),
        }
        labels = {
            'full_name': 'الاسم بالكامل',
            'employee_id': 'كود الموظف (على جهاز البصمة)',
            'department': 'القسم',
            'job_title': 'المسمى الوظيفي',
            'phone_number': 'رقم الهاتف',
            'email': 'البريد الإلكتروني',
            'address': 'العنوان',
            'gender': 'الجنس',
            'birth_date': 'تاريخ الميلاد',
            'hire_date': 'تاريخ التعيين',
            'salary': 'الراتب',
            'work_start_time': 'وقت بدء العمل',
            'work_end_time': 'وقت انتهاء العمل',
            'photo': 'صورة الموظف',
            'id_face_image': 'صورة وجه البطاقة',
            'id_back_image': 'صورة ظهر البطاقة',
            'is_active': 'الموظف نشط',
        }

    def __init__(self, *args, **kwargs):
        """
        Add Bootstrap classes to form fields and set queryset for department.
        """
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.all()
        # Apply form-control class to all fields
        for field_name, field in self.fields.items():
            if field.widget.attrs.get('class'):
                field.widget.attrs['class'] += ' form-control'
            else:
                field.widget.attrs['class'] = 'form-control'
