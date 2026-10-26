import frappe

from face_checkin.api import describe_last_checkin, get_employee

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/checkin"
		raise frappe.Redirect

	context.no_cache = 1
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.employee = get_employee()
	context.last_checkin = describe_last_checkin(context.employee.name) if context.employee else ""
