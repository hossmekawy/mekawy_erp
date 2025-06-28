from django.core.management.base import BaseCommand
from django.db import transaction
from suppliers.models import Supplier, SupplierContact
import csv
import os

class Command(BaseCommand):
    help = 'استيراد بيانات الموردين من ملف CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='مسار ملف CSV')
        parser.add_argument(
            '--update',
            action='store_true',
            help='تحديث الموردين الموجودين',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        update_existing = options['update']

        if not os.path.exists(csv_file):
            self.stdout.write(
                self.style.ERROR(f'الملف غير موجود: {csv_file}')
            )
            return

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                created_count = 0
                updated_count = 0
                error_count = 0

                with transaction.atomic():
                    for row_num, row in enumerate(reader, start=2):
                        try:
                            self.process_supplier_row(
                                row, update_existing, 
                                created_count, updated_count
                            )
                        except Exception as e:
                            error_count += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f'خطأ في السطر {row_num}: {str(e)}'
                                )
                            )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'تم إنشاء {created_count} مورد جديد'
                    )
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'تم تحديث {updated_count} مورد موجود'
                    )
                )
                if error_count > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'حدثت أخطاء في {error_count} سطر'
                        )
                    )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'خطأ في قراءة الملف: {str(e)}')
            )

    def process_supplier_row(self, row, update_existing, created_count, updated_count):
        """معالجة سطر واحد من بيانات المورد"""
        required_fields = ['name', 'code', 'supplier_type']
        for field in required_fields:
            if not row.get(field):
                raise ValueError(f'الحقل {field} مطلوب')

        supplier_data = {
            'name': row['name'],
            'code': row['code'],
            'supplier_type': row['supplier_type'],
            'contact_person': row.get('contact_person', ''),
            'phone': row.get('phone', ''),
            'email': row.get('email', ''),
            'address': row.get('address', ''),
            'city': row.get('city', ''),
            'country': row.get('country', ''),
            'tax_number': row.get('tax_number', ''),
            'payment_terms': row.get('payment_terms', 30),
            'credit_limit': row.get('credit_limit', 0),
            'notes': row.get('notes', ''),
        }

        # تنظيف البيانات
        if supplier_data['payment_terms']:
            supplier_data['payment_terms'] = int(supplier_data['payment_terms'])
        if supplier_data['credit_limit']:
            supplier_data['credit_limit'] = float(supplier_data['credit_limit'])

        # إنشاء أو تحديث المورد
        supplier, created = Supplier.objects.get_or_create(
            code=supplier_data['code'],
            defaults=supplier_data
        )

        if created:
            created_count += 1
            self.stdout.write(f'تم إنشاء المورد: {supplier.name}')
        elif update_existing:
            for key, value in supplier_data.items():
                if key != 'code':  # لا نحدث الكود
                    setattr(supplier, key, value)
            supplier.save()
            updated_count += 1
            self.stdout.write(f'تم تحديث المورد: {supplier.name}')

        # إضافة جهة اتصال إضافية إذا وجدت
        if row.get('contact_name') and row.get('contact_phone'):
            SupplierContact.objects.get_or_create(
                supplier=supplier,
                name=row['contact_name'],
                defaults={
                    'phone': row['contact_phone'],
                    'email': row.get('contact_email', ''),
                    'position': row.get('contact_position', ''),
                    'is_primary': True,
                }
            )