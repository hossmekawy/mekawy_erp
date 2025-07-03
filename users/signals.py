from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import User, UserProfile

@receiver(post_save, sender=User)
def manage_user_on_save(sender, instance, created, **kwargs):
    """
    Consolidated signal handler for the User model.
    - On creation, ensures a UserProfile exists.
    - On any save, syncs the user's role to their assigned Group.
    """
    # 1. On creation, ensure a UserProfile exists. This combines the logic
    #    from the old `create_user_profile` and `save_user_profile` signals.
    if created:
        UserProfile.objects.get_or_create(user=instance)

    # 2. Always sync the user's role to their group membership.
    if instance.role:
        try:
            # Find the group that matches the user's role.
            group, group_created = Group.objects.get_or_create(name=instance.role)
            
            # Use set() to ensure the user belongs *only* to their designated role group.
            # This removes them from any other groups they might have been in.
            instance.groups.set([group])
        except Group.DoesNotExist:
            # This case is unlikely if your migration ran, but it's safe to handle.
            # If a role exists on the user that doesn't have a matching group,
            # remove the user from all groups.
            instance.groups.clear()
