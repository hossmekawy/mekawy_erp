from django.db import migrations

def create_groups_and_permissions(apps, schema_editor):
    """
    Creates user groups and assigns a baseline of permissions.
    """
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    # === Define Roles ===
    roles = [
        'admin', 'manager', 'warehouse_manager', 'warehouse_employee', 
        'production_manager', 'accountant', 'employee', 'viewer'
    ]
    for role_name in roles:
        Group.objects.get_or_create(name=role_name)

    # === Assign Permissions for Warehouse Roles ===
    
    # --- Warehouse Manager Permissions ---
    wh_manager_group = Group.objects.get(name='warehouse_manager')
    wh_manager_permissions = []
    
    # Define models they can manage
    wh_models = ['category', 'product', 'warehouse', 'stockitem', 'stockmovement', 'stocktransfer', 'unit', 'unitconversion']
    for model_name in wh_models:
        try:
            ct = ContentType.objects.get(app_label='warehouses', model=model_name)
            # Managers get all permissions for these models
            wh_manager_permissions.extend(list(Permission.objects.filter(content_type=ct)))
        except ContentType.DoesNotExist:
            # This can happen if the warehouses app hasn't been migrated yet.
            # It's safe to pass in this context.
            pass
    
    wh_manager_group.permissions.set(wh_manager_permissions)


    # --- Warehouse Employee Permissions ---
    wh_employee_group = Group.objects.get(name='warehouse_employee')
    wh_employee_permissions = []

    # Define models and the specific actions they can take
    employee_perms_map = {
        'category': ['view_category'],
        'product': ['view_product'],
        'warehouse': ['view_warehouse'],
        'stockitem': ['view_stockitem', 'add_stockitem', 'change_stockitem'],
        'stockmovement': ['view_stockmovement', 'add_stockmovement'],
        'stocktransfer': ['view_stocktransfer', 'add_stocktransfer'],
        'unit': ['view_unit'],
        'unitconversion': ['view_unitconversion'],
    }

    for model_name, perm_codenames in employee_perms_map.items():
        try:
            ct = ContentType.objects.get(app_label='warehouses', model=model_name)
            wh_employee_permissions.extend(list(Permission.objects.filter(content_type=ct, codename__in=perm_codenames)))
        except ContentType.DoesNotExist:
            pass

    wh_employee_group.permissions.set(wh_employee_permissions)

    # --- Viewer Permissions ---
    viewer_group = Group.objects.get(name='viewer')
    viewer_permissions = []
    viewer_models = ['category', 'product', 'warehouse', 'stockitem']
    for model_name in viewer_models:
        try:
            ct = ContentType.objects.get(app_label='warehouses', model=model_name)
            # Viewers can only view
            viewer_permissions.extend(list(Permission.objects.filter(content_type=ct, codename__startswith='view_')))
        except ContentType.DoesNotExist:
            pass
    
    viewer_group.permissions.set(viewer_permissions)


def remove_groups_and_permissions(apps, schema_editor):
    """
    This function is the reverse of the above. It removes the created groups.
    """
    Group = apps.get_model('auth', 'Group')
    roles = [
        'admin', 'manager', 'warehouse_manager', 'warehouse_employee', 
        'production_manager', 'accountant', 'employee', 'viewer'
    ]
    # Delete the groups
    Group.objects.filter(name__in=roles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # The second argument to RunPython is the function to run when un-migrating
        migrations.RunPython(create_groups_and_permissions, remove_groups_and_permissions),
    ]
