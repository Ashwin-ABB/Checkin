import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Employee Checkin": [
		{
			"fieldname": "fc_section",
			"label": "Face Check-in",
			"fieldtype": "Section Break",
			"insert_after": "device_id",
			"collapsible": 1,
		},
		{
			"fieldname": "fc_photo",
			"label": "Check-in Photo",
			"fieldtype": "Attach Image",
			"insert_after": "fc_section",
			"read_only": 1,
		},
		{
			"fieldname": "fc_match_status",
			"label": "Match Status",
			"fieldtype": "Select",
			"options": "Not Checked\nMatched\nReview\nFailed",
			"default": "Not Checked",
			"insert_after": "fc_photo",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "fc_match_score",
			"label": "Match Score",
			"fieldtype": "Float",
			"precision": "2",
			"insert_after": "fc_match_status",
			"read_only": 1,
		},
		{
			"fieldname": "fc_col",
			"fieldtype": "Column Break",
			"insert_after": "fc_match_score",
		},
		{
			"fieldname": "fc_latitude",
			"label": "Latitude",
			"fieldtype": "Float",
			"precision": "9",
			"insert_after": "fc_col",
			"read_only": 1,
		},
		{
			"fieldname": "fc_longitude",
			"label": "Longitude",
			"fieldtype": "Float",
			"precision": "9",
			"insert_after": "fc_latitude",
			"read_only": 1,
		},
		{
			"fieldname": "fc_accuracy",
			"label": "Location Accuracy (m)",
			"fieldtype": "Float",
			"precision": "1",
			"insert_after": "fc_longitude",
			"read_only": 1,
		},
		{
			"fieldname": "fc_distance",
			"label": "Distance From Shift Location (m)",
			"fieldtype": "Float",
			"precision": "1",
			"insert_after": "fc_accuracy",
			"read_only": 1,
		},
	]
}


def after_install():
	if not frappe.db.exists("DocType", "Employee Checkin"):
		frappe.throw("Face Checkin needs Frappe HR (hrms) to be installed first.")
	create_custom_fields(CUSTOM_FIELDS, update=True)


def after_migrate():
	if frappe.db.exists("DocType", "Employee Checkin"):
		create_custom_fields(CUSTOM_FIELDS, update=True)
