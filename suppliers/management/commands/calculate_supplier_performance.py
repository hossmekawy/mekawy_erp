from django.core.management.base import BaseCommand
from django.utils import timezone
from suppliers.models import Supplier, SupplierPerformanceMetric
import datetime

class Command(BaseCommand):
    help = 'حساب مقاييس أداء الموردين'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months',
            type=int,
            default=1,
            help='عدد الأشهر للحساب (افتراضي: 1)',
        )
        parser.add_argument(
            '--supplier-id',
            type=int,
            help='معرف مورد محدد',
        )

    def handle(self, *args, **options):
        months = options['months']
        supplier_id = options.get('supplier_id')

        # تحديد الفترة الزمنية
        end_date = timezone.now().date()
        start_date = end_date.replace(day=1)
        
        for i in range(months):
            if i > 0:
                start_date = start_date - datetime.timedelta(days=1)
                start_date = start_date.replace(day=1)

        # تحديد الموردين
        if supplier_id:
            suppliers = Supplier.objects.filter(id=supplier_id, is_active=True)
        else:
            suppliers = Supplier.objects.filter(is_active=True)

        calculated_count = 0
        
        for supplier in suppliers:
            try:
                # حساب المقاييس لكل شهر
                current_start = start_date
                
                for month in range(months):
                    # تحديد نهاية الشهر
                    if current_start.month == 12:
                        current_end = current_start.replace(
                            year=current_start.year + 1, 
                            month=1, 
                            day=1
                        ) - datetime.timedelta(days=1)
                    else:
                        current_end = current_start.replace(
                            month=current_start.month + 1, 
                            day=1
                        ) - datetime.timedelta(days=1)

                    # إنشاء أو تحديث المقياس
                    metric, created = SupplierPerformanceMetric.objects.get_or_create(
                        supplier=supplier,
                        period_start=current_start,
                        period_end=current_end
                    )
                    
                    metric.calculate_metrics()
                    calculated_count += 1
                    
                    action = "تم إنشاء" if created else "تم تحديث"
                    self.stdout.write(
                        f'{action} مقياس أداء {supplier.name} '
                        f'للفترة {current_start} - {current_end}'
                    )

                    # الانتقال للشهر التالي
                    if current_start.month == 12:
                        current_start = current_start.replace(
                            year=current_start.year + 1, 
                            month=1
                        )
                    else:
                        current_start = current_start.replace(
                            month=current_start.month + 1
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'خطأ في حساب مقاييس {supplier.name}: {str(e)}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'تم حساب {calculated_count} مقياس أداء'
            )
        )