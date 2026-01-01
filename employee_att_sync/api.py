import frappe
from zk import ZK
from employee_att_sync.tasks import sync_device_logs, update_shift_sync_timestamps

@frappe.whitelist()
def test_device_connection(ip, port):
    """
    Invoked from the 'Att Devices' Form to verify network connectivity.
    Uses the IP and Port fields from the document.
    """
    try:
        # Initialize connection with a short 10s timeout for UI responsiveness
        zk = ZK(ip, port=int(port) if port else 4370, timeout=10)
        conn = zk.connect()
        
        if conn:
            # Retrieve basic device info to confirm full protocol support
            firmware = conn.get_firmware_version()
            conn.disconnect()
            return {
                "status": "success",
                "message": f"Connected successfully! Firmware: {firmware}"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Connection failed: {str(e)}"
        }

@frappe.whitelist()
def trigger_manual_sync():
    setup = frappe.get_single("Attendance Sync Setup")
    if not setup.enabled:
        frappe.throw("La synchronisation est désactivée dans la configuration.")

    devices = frappe.get_all("Att Devices", filters={"disabled": 0}, fields=["name", "device_id"])
    
    if not devices:
        frappe.msgprint("Aucun appareil actif trouvé.")
        return

    total = len(devices)
    
    for i, d in enumerate(devices):
        frappe.publish_progress(
            float(i + 1) / total * 100, 
            title="Synchronisation en cours...", 
            description=f"Traitement de l'appareil : {d.device_id}"
        )

        device_doc = frappe.get_doc("Att Devices", d.name)
        try:
            sync_device_logs(device_doc)
        except Exception:
            frappe.log_error(title=f"Manual Sync Failed: {d.device_id}", message=frappe.get_traceback())

    # Finalisation
    update_shift_sync_timestamps()
    
    frappe.msgprint(f"Synchronisation terminée pour {total} appareils.")


@frappe.whitelist()
def trigger_manual_sync_old():
    """
    Invoked from 'Attendance Sync Setup' to start a sync immediately.
    This runs the same logic as the background scheduler.
    """
    setup = frappe.get_single("Attendance Sync Setup")
    if not setup.enabled:
        frappe.throw("Sync is currently disabled in Setup.")

    # Fetch all active devices
    devices = frappe.get_all("Att Devices", filters={"disabled": 0}, fields=["name"])
    
    if not devices:
        frappe.msgprint("No active devices found to sync.")
        return

    count = 0
    for d in devices:
        device_doc = frappe.get_doc("Att Devices", d.name)
        try:
            # Reusing the logic defined in tasks.py
            sync_device_logs(device_doc)
            count += 1
        except Exception as e:
            frappe.log_error(title=f"Manual Sync Failed: {device_doc.device_id}", message=frappe.get_traceback())

    # Update Shift Type markers in HRMS
    update_shift_sync_timestamps()
    
    frappe.msgprint(f"Sync completed for {count} devices. Check 'Employee Checkins' for new logs.")
