from django.db.models import Avg, Count
from .models import Supplier, SupplierRating

def rating_context(request):
    """Add rating-related context to all templates"""
    
    if not request.user.is_authenticated:
        return {}
    
    # Get pending ratings count
    from django.utils import timezone
    from datetime import timedelta
    
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    pending_ratings_count = PurchaseOrder.objects.filter(
        status='completed',
        actual_delivery_date__gte=thirty_days_ago,
        ratings__isnull=True,
        created_by=request.user
    ).count()
    
    # Get user's recent ratings
    user_recent_ratings = SupplierRating.objects.filter(
        rated_by=request.user
    ).select_related('supplier').order_by('-rating_date')[:5]
    
    # Overall rating statistics
    total_suppliers_with_ratings = Supplier.objects.filter(
        current_rating__gt=0,
        is_active=True
    ).count()
    
    avg_rating_all_suppliers = Supplier.objects.filter(
        current_rating__gt=0,
        is_active=True
    ).aggregate(avg=Avg('current_rating'))['avg'] or 0
    
    return {
        'rating_context': {
            'pending_ratings_count': pending_ratings_count,
            'user_recent_ratings': user_recent_ratings,
            'total_suppliers_with_ratings': total_suppliers_with_ratings,
            'avg_rating_all_suppliers': round(avg_rating_all_suppliers, 2)
        }
    }