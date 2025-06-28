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