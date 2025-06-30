from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView, ListView
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from .models import User, UserProfile
from .forms import CustomUserCreationForm, CustomAuthenticationForm, UserProfileForm, UserEditForm, UserProfileSettingsForm

class CustomLoginView(LoginView):
    form_class = CustomAuthenticationForm
    template_name = 'users/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('dashboard:index')
    
    def form_valid(self, form):
        messages.success(self.request, f'مرحباً بك مجدداً, {form.get_user().first_name}!')
        return super().form_valid(form)

class CustomLogoutView(LogoutView):
    # The next_page attribute is used by the default GET handler if we were to use it.
    # We will handle redirection manually for clarity.
    next_page = reverse_lazy('users:login')

    def dispatch(self, request, *args, **kwargs):
        # This is the key change. We handle the GET request directly here.
        if request.method == 'GET':
            messages.info(request, 'تم تسجيل الخروج بنجاح.')
            logout(request)
            return HttpResponseRedirect(self.next_page)
        
        # The default POST handler remains unchanged.
        messages.info(request, 'تم تسجيل الخروج بنجاح.')
        return super().dispatch(request, *args, **kwargs)


class RegisterView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:manage')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(self.request, 'ليس لديك صلاحية للوصول لهذه الصفحة.')
        return redirect('dashboard:index')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, 
            f'تم إنشاء حساب {self.object.full_name} بنجاح! الدور المخصص: {self.object.get_role_display()}'
        )
        return response

class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'users/password_change.html'
    success_url = reverse_lazy('users:password_change_done')

    def form_valid(self, form):
        messages.success(self.request, 'تم تغيير كلمة المرور بنجاح!')
        return super().form_valid(form)

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'users/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.request.user.profile
        return context

class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = 'users/profile_edit.html'
    success_url = reverse_lazy('users:profile')
    
    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "تعديل الملف الشخصي"
        if 'profile_settings_form' not in context:
            context['profile_settings_form'] = UserProfileSettingsForm(instance=self.request.user.profile)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = UserProfileForm(request.POST, request.FILES, instance=self.object)
        profile_settings_form = UserProfileSettingsForm(request.POST, instance=self.object.profile)

        if form.is_valid() and profile_settings_form.is_valid():
            form.save()
            profile_settings_form.save()
            messages.success(self.request, 'تم تحديث الملف الشخصي بنجاح!')
            return redirect(self.get_success_url())
        else:
            return self.render_to_response(
                self.get_context_data(form=form, profile_settings_form=profile_settings_form)
            )

class UserManagementView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = 'users/user_management.html'
    context_object_name = 'users'
    paginate_by = 15
    
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.role == 'manager'
    
    def get_queryset(self):
        return User.objects.all().order_by('-created_at')

class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:manage')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'إنشاء مستخدم جديد'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء المستخدم بنجاح!')
        return super().form_valid(form)

class UserEditView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:manage')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'تعديل المستخدم: {self.object.full_name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'تم تحديث بيانات {self.object.full_name} بنجاح!')
        return super().form_valid(form)

class UserDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = User
    template_name = 'users/user_confirm_delete.html'
    success_url = reverse_lazy('users:manage')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def post(self, request, *args, **kwargs):
        user_to_delete = self.get_object()
        if user_to_delete == request.user:
            messages.error(request, 'لا يمكنك حذف حسابك الخاص!')
            return redirect('users:manage')
        
        messages.success(request, f'تم حذف المستخدم {user_to_delete.full_name} بنجاح.')
        return super().post(request, *args, **kwargs)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def toggle_user_active(request, pk):
    user_to_toggle = get_object_or_404(User, pk=pk)
    if user_to_toggle == request.user:
        messages.error(request, 'لا يمكنك تغيير حالة حسابك الخاص.')
    else:
        user_to_toggle.is_active = not user_to_toggle.is_active
        user_to_toggle.save()
        status = "تفعيل" if user_to_toggle.is_active else "حظر"
        messages.success(request, f'تم {status} حساب المستخدم {user_to_toggle.full_name} بنجاح.')
    return redirect('users:manage')
