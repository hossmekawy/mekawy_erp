from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.CustomerListView.as_view(), name='customer_list'),
    path('create/', views.CustomerCreateView.as_view(), name='customer_create'),
    path('<int:pk>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    path('<int:pk>/update/', views.CustomerUpdateView.as_view(), name='customer_update'),
    path('<int:pk>/add-interaction/', views.add_interaction, name='add_interaction'),
    path('api/search/', views.CustomerSearchAPIView.as_view(), name='api_customer_search'),
    path('api/create/', views.CustomerCreateAPIView.as_view(), name='api_customer_create'),


]
