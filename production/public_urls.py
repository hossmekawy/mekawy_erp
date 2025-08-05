# production/public_urls.py
from django.urls import path
from . import views

# These URLs are NOT namespaced and are intended to be included at the root level of your project.
# They are specifically for public-facing pages that do not require login.
urlpatterns = [
    path('track/<str:order_number>/', views.public_order_detail_view, name='public_order_detail'),
]
