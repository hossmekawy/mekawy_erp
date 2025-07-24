import sys
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from zk import ZK, const

from hr.models import Employee, Attendance

# !!! IMPORTANT !!!
# Fill in your ZKTeco device's details here
DEVICE_IP = '192.168.1.52'  # <-- CHANGE THIS TO YOUR DEVICE'S IP ADDRESS
DEVICE_PORT = 4370            # <-- Default port, change if needed
DEVICE_PASSWORD = 0           # <-- Default is 0, change if you set one

class Command(BaseCommand):
    help = 'Efficiently fetches attendance data from the ZKTeco device and saves it to the database.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Connecting to ZKTeco device..."))
        
        zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=10, password=DEVICE_PASSWORD, force_udp=False, ommit_ping=False)
        conn = None
        try:
            # Connect to the device
            conn = zk.connect()
            self.stdout.write(self.style.SUCCESS(f"Successfully connected to device! Firmware: {conn.get_firmware_version()}"))
            
            # Disable device while processing
            conn.disable_device()

            # Get all attendance records from the device
            attendance_logs = conn.get_attendance()
            
            if not attendance_logs:
                self.stdout.write(self.style.WARNING("No new attendance logs found on the device."))
                return

            self.stdout.write(self.style.SUCCESS(f"Found {len(attendance_logs)} logs. Processing with optimized method..."))
            
            # --- OPTIMIZATION START ---

            # Step 1: Fetch ALL employees into a dictionary for quick lookups.
            # This avoids hitting the database for each log record.
            all_employees = {emp.employee_id: emp for emp in Employee.objects.all()}
            self.stdout.write(f"Loaded {len(all_employees)} total employees from the database for matching.")

            # Step 2: Process logs in memory to find the first and last punch for each employee each day.
            daily_punches = defaultdict(lambda: {'check_in': None, 'check_out': None})

            for log in attendance_logs:
                employee_id_str = str(log.user_id)
                employee_obj = all_employees.get(employee_id_str)

                # --- IMPROVED LOGGING ---
                # Case 1: Employee does not exist in the database at all.
                if not employee_obj:
                    self.stdout.write(self.style.WARNING(f"Skipping log: Employee with ID '{employee_id_str}' not found in database. Please sync employees."))
                    continue
                
                # Case 2: Employee exists but is marked as inactive.
                if not employee_obj.is_active:
                    self.stdout.write(self.style.NOTICE(f"Skipping log: Employee '{employee_obj.full_name}' (ID: {employee_id_str}) is marked as inactive."))
                    continue
                # --- END IMPROVED LOGGING ---
                
                # Make the timestamp from the device timezone-aware
                log_datetime_aware = timezone.make_aware(log.timestamp)
                log_date = log_datetime_aware.date()
                
                key = (employee_id_str, log_date)
                punches = daily_punches[key]
                
                # Determine the earliest punch (check-in)
                if punches['check_in'] is None or log_datetime_aware < punches['check_in']:
                    punches['check_in'] = log_datetime_aware
                
                # Determine the latest punch (check-out)
                if punches['check_out'] is None or log_datetime_aware > punches['check_out']:
                    punches['check_out'] = log_datetime_aware

            # If a day has only one punch, it's a check-in. The max and min will be the same.
            for key, punches in daily_punches.items():
                if punches['check_in'] == punches['check_out']:
                    punches['check_out'] = None

            self.stdout.write(f"Consolidated logs into {len(daily_punches)} unique daily records for active employees.")

            # Step 3: Fetch existing attendance records to update.
            if not daily_punches:
                self.stdout.write(self.style.SUCCESS("No attendance logs for active employees to process."))
                return

            employee_ids_to_process = {key[0] for key in daily_punches.keys()}
            dates_to_process = {key[1] for key in daily_punches.keys()}
            
            existing_records = Attendance.objects.filter(
                employee__employee_id__in=employee_ids_to_process,
                date__in=dates_to_process
            ).select_related('employee')

            existing_map = {(record.employee.employee_id, record.date): record for record in existing_records}
            self.stdout.write(f"Found {len(existing_map)} existing records in the database to compare against.")
            
            # Step 4: Determine which records to create and which to update.
            records_to_create = []
            records_to_update = []

            for key, punches in daily_punches.items():
                employee_id_str, log_date = key
                employee_obj = all_employees[employee_id_str]
                
                existing_record = existing_map.get(key)
                
                if existing_record:
                    if existing_record.check_in != punches['check_in'] or existing_record.check_out != punches['check_out']:
                        existing_record.check_in = punches['check_in']
                        existing_record.check_out = punches['check_out']
                        records_to_update.append(existing_record)
                else:
                    records_to_create.append(
                        Attendance(employee=employee_obj, date=log_date, check_in=punches['check_in'], check_out=punches['check_out'])
                    )

            # Step 5: Perform bulk database operations.
            if records_to_create:
                Attendance.objects.bulk_create(records_to_create)
                self.stdout.write(self.style.SUCCESS(f"Created {len(records_to_create)} new attendance records."))

            if records_to_update:
                Attendance.objects.bulk_update(records_to_update, ['check_in', 'check_out'])
                self.stdout.write(self.style.SUCCESS(f"Updated {len(records_to_update)} existing attendance records."))

            if not records_to_create and not records_to_update:
                self.stdout.write(self.style.SUCCESS("Database is already up-to-date. No changes were needed."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))
        finally:
            if conn:
                conn.enable_device()
                conn.disconnect()
                self.stdout.write(self.style.SUCCESS("Device disconnected and enabled."))
