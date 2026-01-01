// Copyright (c) 2025, HALFWARE and contributors
// For license information, please see license.txt

frappe.ui.form.on('Attendance Sync Setup', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Now'), function() {
            frappe.show_alert({message: __('Starting Sync...'), indicator: 'blue'});
            frappe.call({
                method: "employee_att_sync.api.trigger_manual_sync",
                callback: function(r) {
                    frm.reload_doc();
                }
            });
        });
    }
});
