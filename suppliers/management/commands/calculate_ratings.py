from django.core.management.base import BaseCommand
from django.db.models import Avg
from suppliers.models import Supplier, SupplierRating

class Command(BaseCommand):
    help = 'Calculate and update supplier ratings'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--supplier-id',
            type=int,
            help='Calculate rating for specific supplier ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation even if rating exists',
        )
    
    def handle(self, *args, **options):
        supplier_id = options.get('supplier_id')
        force = options.get('force', False)
        
        if supplier_id:
            try:
                supplier = Supplier.objects.get(id=supplier_id)
                suppliers = [supplier]
                self.stdout.write(f'Processing supplier: {supplier.name}')
            except Supplier.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Supplier with ID {supplier_id} not found')
                )
                return
        else:
            suppliers = Supplier.objects.all()
            self.stdout.write(f'Processing {suppliers.count()} suppliers')
        
        updated_count = 0
        
        for supplier in suppliers:
            old_rating = supplier.current_rating
            
            # Calculate new average rating
            avg_rating = supplier.ratings.aggregate(
                avg=Avg('overall_rating')
            )['avg']
            
            new_rating = round(avg_rating, 2) if avg_rating else 0
            
            if force or old_rating != new_rating:
                supplier.current_rating = new_rating
                supplier.save(update_fields=['current_rating'])
                updated_count += 1
                
                self.stdout.write(
                    f'Updated {supplier.name}: {old_rating} -> {new_rating}'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated_count} supplier ratings'
            )
        )