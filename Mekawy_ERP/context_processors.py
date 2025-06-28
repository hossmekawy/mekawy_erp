from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

def global_context(request):
    """
    إضافة متغيرات عامة لجميع القوالب
    """
    context = {
        'current_year': timezone.now().year,
        'current_date': timezone.now().date(),
        'current_time': timezone.now().time(),
    }
    
    # إضافة عدد المستخدمين المتصلين (يمكن تطويرها لاحقاً)
    if request.user.is_authenticated:
        context['online_users_count'] = User.objects.filter(is_active=True).count()
        context['last_update'] = timezone.now().strftime('%H:%M:%S')
    
    return context