import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from zk import ZK, const

from hr.models import Employee, Department

# !!! IMPORTANT !!!
# Fill in your ZKTeco device's details here
DEVICE_IP = '192.168.1.52'  # <-- CHANGE THIS TO YOUR DEVICE'S IP ADDRESS
DEVICE_PORT = 4370            # <-- Default port, change if needed
DEVICE_PASSWORD = 0           # <-- Default is 0, change if you set one

class Command(BaseCommand):
    help = 'Fetches users from the ZKTeco device and creates new employees without overwriting existing data.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Connecting to ZKTeco device to sync users..."))
        
        zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=DEVICE_PASSWORD, force_udp=False, ommit_ping=False)
        conn = None
        try:
            # Connect to the device
            conn = zk.connect()
            self.stdout.write(self.style.SUCCESS(f"Successfully connected to device! Firmware: {conn.get_firmware_version()}"))
            
            # Disable device while processing
            conn.disable_device()

            # Get all users from the device
            device_users = conn.get_users()
            
            if not device_users:
                self.stdout.write(self.style.WARNING("No users found on the device."))
                return

            self.stdout.write(self.style.SUCCESS(f"Found {len(device_users)} users on the device. Syncing with database..."))
            
            created_count = 0
            skipped_count = 0
            
            # Get the default department or create it if it doesn't exist
            default_department, _ = Department.objects.get_or_create(name='غير محدد')

            for user in device_users:
                try:
                    employee_id_str = str(user.user_id)
                    
                    if not employee_id_str:
                        self.stdout.write(self.style.WARNING(f"Skipping user with empty user_id (Name: {user.name}, UID: {user.uid})."))
                        continue

                    if not user.name:
                        self.stdout.write(self.style.WARNING(f"Skipping user with empty name (ID: {employee_id_str})."))
                        continue

                    # --- FIX: Use get_or_create ---
                    # This will only create a new employee if one with the same employee_id
                    # does not already exist. It will NOT update existing records.
                    employee, created = Employee.objects.get_or_create(
                        employee_id=employee_id_str,
                        defaults={
                            'full_name': user.name,
                            'job_title': 'موظف', # Default job title
                            'department': default_department,
                            'hire_date': date.today(), # Set hire date to today, can be edited later
                            'is_active': True,
                        }
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f"Created new employee: {user.name} (ID: {employee_id_str})"))
                    else:
                        skipped_count += 1
                        # This log message is intentionally omitted to avoid clutter,
                        # but you can uncomment it for debugging if needed.
                        # self.stdout.write(f"Skipped existing employee: {user.name} (ID: {employee_id_str})")

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error processing user {user.name} (ID: {user.user_id}): {e}"))

            self.stdout.write(self.style.SUCCESS(f"Sync complete! Created: {created_count}, Skipped (already exist): {skipped_count}"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to connect or process data: {e}"))
        finally:
            if conn:
                # Re-enable the device
                conn.enable_device()
                conn.disconnect()
                self.stdout.write(self.style.SUCCESS("Device disconnected and enabled."))
