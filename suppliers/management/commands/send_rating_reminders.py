from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from suppliers.models import PurchaseOrder

class Command(BaseCommand):
    help = 'Send rating reminders for completed orders'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back for completed orders (default: 7)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually sending reminders',
        )
    
    def handle(self, *args, **options):
        days = options.get('days', 7)
        dry_run = options.get('dry_run', False)
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get completed orders without ratings
        orders_without_ratings = PurchaseOrder.objects.filter(
            status='completed',
            actual_delivery_date__range=[start_date, end_date],
            ratings__isnull=True
        ).select_related('supplier', 'created_by')
        
        self.stdout.write(
            f'Found {orders_without_ratings.count()} orders needing rating reminders'
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No reminders will be sent'))
        
        reminder_count = 0
        
        for order in orders_without_ratings:
            if dry_run:
                self.stdout.write(
                    f'Would send reminder for: {order.po_number} - {order.supplier.name} '
                    f'(completed: {order.actual_delivery_date})'
                )
            else:
                # Here you would implement actual reminder sending
                # For example, send email or create notification
                self.send_rating_reminder(order)
                
            reminder_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Would send {reminder_count} reminders')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Sent {reminder_count} rating reminders')
            )
    
    def send_rating_reminder(self, order):
        """Send rating reminder for a specific order"""
        # Implement your notification/email sending logic here
        # For now, just log it
        self.stdout.write(
            f'Reminder sent for order {order.po_number} to {order.created_by.username}'
        )