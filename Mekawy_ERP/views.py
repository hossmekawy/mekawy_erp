from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

def home_view(request):
    """
    Root URL handler - redirects based on authentication status
    """
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    else:
        return redirect('users:login')
    
from django.shortcuts import render

def custom_page_not_found_view(request, exception):
    """
    Custom view for handling 404 Page Not Found errors.
    """
    return render(request, '404.html', status=404)

def custom_server_error_view(request):
    """
    Custom view for handling 500 Internal Server errors.
    """
    return render(request, '500.html', status=500)
