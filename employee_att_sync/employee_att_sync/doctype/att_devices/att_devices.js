// Copyright (c) 2025, HALFWARE and contributors
// For license information, please see license.txt

frappe.ui.form.on('Att Devices', {
    refresh: function(frm) {
        frm.add_custom_button(__('Test Connection'), function() {
            frappe.call({
                method: "employee_att_sync.api.test_device_connection",
                args: {
                    ip: frm.doc.ip,
                    port: frm.doc.port
                },
                callback: function(r) {
                    if (r.message.status === "success") {
                        frappe.msgprint({title: __('Success'), message: r.message.message, indicator: 'green'});
                    } else {
                        frappe.msgprint({title: __('Failed'), message: r.message.message, indicator: 'red'});
                    }
                }
            });
        });
    }
});
