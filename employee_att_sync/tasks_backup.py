import frappe
from zk import ZK  # Ensure pyzk is installed: pip install pyzk
from frappe.utils import get_datetime, now_datetime

# HRMS/ERPNext standard error messages for filtering
EMPLOYEE_NOT_FOUND = "No Employee found for the given employee User ID"
DUPLICATE_CHECKIN = "Duplicate Employee Checkin found"

def execute_sync():
    """
    Main scheduler entry point. 
    Synchronizes all devices and updates shift sync timestamps.
    """
    setup = frappe.get_single("Attendance Sync Setup")
    if not setup.enabled:
        return

    # Fetch all devices that are NOT disabled
    # Fields: device_id, ip, port, import_from_date, disabled
    devices = frappe.get_all("Att Devices", filters={"disabled": 0}, fields=["*"])
    
    for device in devices:
        try:
            sync_device_logs(device)
        except Exception:
            # Logs device-specific connection or protocol errors to Frappe Error Log
            frappe.log_error(
                title=f"Empployee Att Sync Failed: {device.device_id}",
                message=frappe.get_traceback()
            )

    # Update 'Last Sync of Checkin' for all configured shifts
    update_shift_sync_timestamps()

def sync_device_logs(device):
    """
    Connects to a specific device and pulls attendance data.
    """
    # Uses mandatory fields: IP and Port (defaulting to 4370)
    zk = ZK(device.ip, port=int(device.port) if device.port else 4370, timeout=30)
    conn = None
    
    try:
        conn = zk.connect()
        conn.disable_device() # Stop device interactions during pull
        
        attendances = conn.get_attendance()
        
        if attendances:
            last_sync = frappe.db.get_value("Att Devices", device.name, "last_sync")
            for log in attendances:
                # FILTER: Only process logs from the specified device start date
                if device.import_from_date and log.timestamp.date() < get_datetime(device.import_from_date).date():
                    continue
                if last_sync and log.timestamp <= get_datetime(last_sync):
                    continue
                process_attendance_log(log, device)

        conn.enable_device()
        
        # Save current time as last successful sync on the device record
        frappe.db.set_value("Att Devices", device.name, "last_sync", now_datetime())
        frappe.db.commit()

    finally:
        if conn:
            conn.disconnect()

def process_attendance_log(log, device):
    """
    Validates and inserts an 'Employee Checkin' document into HRMS.
    """
    employee_id = frappe.get_value(
        "Employee",
        {"attendance_device_id": str(log.user_id)},
        "name"
    )

    if not employee_id:
        frappe.log_error(
            title=f"Checkin Failed: Employee Not Found",
            message=f"Device: {device.device_id}\nUser ID pointeuse: {log.user_id}\nLog: {str(log)}"
        )
        return

    # Check for existing records to prevent duplicates in the database
    exists = frappe.db.exists("Employee Checkin", {
        "employee": employee_id,
        "time": log.timestamp,
        "device_id": device.device_id
    })
    
    if not exists:
        try:
            # Create a new HRMS Employee Checkin document
            doc = frappe.get_doc({
                "doctype": "Employee Checkin",
                "employee": employee_id,
                "time": log.timestamp,
                "device_id": device.device_id,
                "log_type": getattr(device, 'punch_direction', None),
                "refresh_attendance": 1 # Tells HRMS to recalculate attendance for this employee
            })
            doc.insert(ignore_permissions=True)
            
        except Exception as e:
            error_msg = str(e)
            # Filter out expected errors to avoid cluttering the Error Log
            if not (DUPLICATE_CHECKIN in error_msg or EMPLOYEE_NOT_FOUND in error_msg):
                frappe.log_error(
                    title=f"Checkin Insertion Failed: {employee_id}",
                    message=f"Device: {device.device_id}\nLog: {str(log)}\nError: {error_msg}"
                )

def update_shift_sync_timestamps():
    """
    Syncs the latest pull time to the standard HRMS 'Shift Type' DocType.
    Uses 'Att Shifts' and 'Att Shifts Devices' child table.
    """
    # Get shift mappings
    shift_mappings = frappe.get_all("Att Shifts", fields=["name", "shift_type"])
    
    for mapping in shift_mappings:
        # Get devices from the child table 'att_devices' using link field 'att_device'
        device_links = frappe.get_all("Att Shifts Devices", 
                                     filters={"parent": mapping.name}, 
                                     fields=["att_device"])
        
        device_names = [d.att_device for d in device_links]
        
        if device_names:
            # Find the minimum (earliest) last sync time across all linked devices

            #min_ts = frappe.db.get_value("Att Devices", 
            #                            {"name": ["in", device_names]}, 
            #                            {"min":"last_sync"})

            result = frappe.db.sql("""
                SELECT MIN(last_sync) as min_ts
                FROM `tabAtt Devices`
                WHERE name IN %s
            """, (device_names,), as_dict=True)

            min_ts = result[0].min_ts if result else None
            if min_ts:
                # Update the standard HRMS Shift Type for automatic processing
                frappe.db.set_value("Shift Type", mapping.shift_type, "last_sync_of_checkin", min_ts)
                frappe.db.commit()
