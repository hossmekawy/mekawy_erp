from django.core.management.base import BaseCommand
from warehouses.models import Unit, UnitConversion

class Command(BaseCommand):
    help = 'Create initial units and conversions'

    def handle(self, *args, **options):
        # Create basic units
        piece, created = Unit.objects.get_or_create(
            name='قطعة',
            defaults={'symbol': 'قطعة', 'is_base_unit': True}
        )
        
        dozen, created = Unit.objects.get_or_create(
            name='دستة',
            defaults={'symbol': 'دستة', 'is_base_unit': False}
        )
        
        sarya6, created = Unit.objects.get_or_create(
            name='ساريه 6',
            defaults={'symbol': 'ساريه6', 'is_base_unit': False}
        )
        
        sarya4, created = Unit.objects.get_or_create(
            name='ساريه 4',
            defaults={'symbol': 'ساريه4', 'is_base_unit': False}
        )
        
        shk48, created = Unit.objects.get_or_create(
            name='شيكارة 48',
            defaults={'symbol': 'شيكارة48', 'is_base_unit': False}
        )
        
        shk30, created = Unit.objects.get_or_create(
            name='شيكارة 30',
            defaults={'symbol': 'شيكارة30', 'is_base_unit': False}
        )

        # Create conversions
        conversions = [
            (dozen, piece, 12),
            (sarya6, piece, 6),
            (sarya4, piece, 4),
            (shk48, piece, 48),
            (shk30, piece, 30),
        ]

        for from_unit, to_unit, factor in conversions:
            UnitConversion.objects.get_or_create(
                from_unit=from_unit,
                to_unit=to_unit,
                defaults={'conversion_factor': factor}
            )

        self.stdout.write(
            self.style.SUCCESS('Successfully created initial units and conversions')
        )