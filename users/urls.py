from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication URLs
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    
    # Registration (Admin only)
    path('register/', views.RegisterView.as_view(), name='register'),
    
    # Password Reset URLs
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='users/password_reset.html',
             email_template_name='users/password_reset_email.html',
             success_url=reverse_lazy('users:password_reset_done')
         ), 
         name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='users/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='users/password_reset_confirm.html',
             success_url=reverse_lazy('users:password_reset_complete')
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='users/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    # NEW: Password Change URLs for logged-in users
    path('password-change/', 
         views.CustomPasswordChangeView.as_view(), 
         name='password_change'),

    path('password-change/done/', 
         auth_views.PasswordChangeDoneView.as_view(
             template_name='users/password_change_done.html'
         ), 
         name='password_change_done'),
    
    # Profile URLs
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    
    # User Management (Admin/Manager only)
    path('manage/', views.UserManagementView.as_view(), name='manage'),
    path('manage/create/', views.UserCreateView.as_view(), name='create_user'),
    path('manage/<int:pk>/edit/', views.UserEditView.as_view(), name='edit_user'),
    path('manage/<int:pk>/delete/', views.UserDeleteView.as_view(), name='delete_user'),
    
    path('manage/<int:pk>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),

]
