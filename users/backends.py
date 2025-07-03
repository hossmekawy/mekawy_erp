from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailOrUsernameBackend(ModelBackend):
    """
    This is a custom authentication backend.
    It allows users to log in using either their username or email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Try to find a user matching either the username or email.
            # The `__iexact` lookup makes the comparison case-insensitive.
            user = UserModel.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between a user existing and not existing. This is a
            # security measure to prevent user enumeration attacks.
            UserModel().set_password(password)
            return
        except UserModel.MultipleObjectsReturned:
            # This case should not happen if your usernames and emails are unique.
            # If it does, it indicates a data integrity issue.
            return

        # Check if the password is correct and the user is allowed to authenticate.
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

    def get_user(self, user_id):
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
