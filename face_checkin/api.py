import base64
import math

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime, get_datetime, getdate, now_datetime

MAX_IMAGE_BYTES = 2 * 1024 * 1024
DUPLICATE_WINDOW_SECONDS = 60


def _conf(key, default=None):
	value = frappe.conf.get(f"face_checkin_{key}")
	return default if value is None else value


def get_employee(user=None):
	"""Active Employee linked to the logged-in user, or None."""
	user = user or frappe.session.user
	fields = ["name", "employee_name", "image"]
	if frappe.get_meta("Employee").has_field("default_shift"):
		fields.append("default_shift")
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, fields, as_dict=True)


def get_last_checkin(employee):
	return frappe.db.get_value(
		"Employee Checkin", {"employee": employee}, ["log_type", "time"], order_by="time desc", as_dict=True
	)


def describe_last_checkin(employee):
	last = get_last_checkin(employee)
	if not last:
		return ""
	label = "Checked in" if last.log_type == "IN" else "Checked out"
	return f"{label} at {format_datetime(last.time, 'hh:mm a, dd MMM')}"


@frappe.whitelist(methods=["POST"])
def checkin(log_type, image, latitude=None, longitude=None, accuracy=None):
	if log_type not in ("IN", "OUT"):
		frappe.throw(_("Log type must be IN or OUT"))

	employee = get_employee()
	if not employee:
		frappe.throw(_("Your login is not linked to an active Employee record. Please contact HR."))

	now = now_datetime()
	_check_duplicate(employee.name, log_type, now)

	content = _decode_image(image)
	lat, lng, acc = _parse_location(latitude, longitude, accuracy)
	distance, outside = _check_geofence(employee, lat, lng, now)

	status, score = _match_face(employee, content)
	hold = cint(_conf("hold_unmatched", 1)) and status in ("Review", "Failed")

	values = {
		"doctype": "Employee Checkin",
		"employee": employee.name,
		"log_type": log_type,
		"time": now,
		"device_id": "Face Check-in",
		"skip_auto_attendance": 1 if (hold or outside) else 0,
		"fc_match_status": status,
		"fc_match_score": score,
		"fc_latitude": lat,
		"fc_longitude": lng,
		"fc_accuracy": acc,
		"fc_distance": distance,
	}

	# Fill the standard HR location fields too, when this version of HR has them
	meta = frappe.get_meta("Employee Checkin")
	if lat is not None:
		if meta.has_field("latitude"):
			values["latitude"] = lat
		if meta.has_field("longitude"):
			values["longitude"] = lng

	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)

	photo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"checkin-{employee.name}-{now:%Y%m%d-%H%M%S}.jpg",
			"attached_to_doctype": "Employee Checkin",
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": content,
		}
	)
	photo.insert(ignore_permissions=True)
	doc.db_set("fc_photo", photo.file_url, update_modified=False)

	return {
		"ok": True,
		"log_type": log_type,
		"time": format_datetime(now, "hh:mm a, dd MMM"),
		"match_status": status,
		"on_hold": bool(hold or outside),
	}


def _check_duplicate(employee, log_type, now):
	last = get_last_checkin(employee)
	if last and last.log_type == log_type:
		if (now - get_datetime(last.time)).total_seconds() < DUPLICATE_WINDOW_SECONDS:
			frappe.throw(_("You have just checked {0}. Please wait a minute before trying again.").format(
				_("in") if log_type == "IN" else _("out")
			))


def _decode_image(data_url):
	if not data_url or "," not in data_url:
		frappe.throw(_("The photo is missing. Please try again."))
	encoded = data_url.split(",", 1)[1]
	try:
		content = base64.b64decode(encoded, validate=True)
	except Exception:
		frappe.throw(_("The photo could not be read. Please try again."))
	if len(content) > MAX_IMAGE_BYTES:
		frappe.throw(_("The photo is too large. Please try again."))
	if not content.startswith(b"\xff\xd8\xff"):
		frappe.throw(_("The photo must be a JPEG image."))
	return content


def _parse_location(latitude, longitude, accuracy):
	required = cint(_conf("require_location", 1))
	try:
		lat, lng = float(latitude), float(longitude)
		valid = -90 <= lat <= 90 and -180 <= lng <= 180
	except (TypeError, ValueError):
		valid = False

	if not valid:
		if required:
			frappe.throw(_("Your location is needed to check in. Allow location access in your browser and try again."))
		return None, None, None

	acc = flt(accuracy) if accuracy not in (None, "") else None
	max_acc = flt(_conf("max_accuracy_m", 150))
	if max_acc and acc is not None and acc > max_acc:
		frappe.throw(
			_("Your location is not accurate enough ({0} m). Move to an open area, wait a few seconds and try again.").format(
				round(acc)
			)
		)
	return lat, lng, acc


def _get_shift_type(employee, on_date):
	rows = frappe.db.sql(
		"""select shift_type from `tabShift Assignment`
		where employee = %s and docstatus = 1 and status = 'Active'
			and start_date <= %s and (end_date is null or end_date >= %s)
		order by start_date desc limit 1""",
		(employee.name, on_date, on_date),
	)
	if rows:
		return rows[0][0]
	return employee.get("default_shift")


def _get_shift_location(shift_type):
	"""Shift location (latitude, longitude, radius in metres) or None if not configured."""
	if not shift_type or not frappe.db.exists("DocType", "Shift Location"):
		return None
	if not frappe.get_meta("Shift Type").has_field("shift_location"):
		return None
	location = frappe.db.get_value("Shift Type", shift_type, "shift_location")
	if not location:
		return None
	meta = frappe.get_meta("Shift Location")
	if not all(meta.has_field(f) for f in ("latitude", "longitude", "checkin_radius")):
		return None
	row = frappe.db.get_value("Shift Location", location, ["latitude", "longitude", "checkin_radius"], as_dict=True)
	if not row or row.latitude is None or row.longitude is None or not row.checkin_radius:
		return None
	return row


def _distance_m(lat1, lon1, lat2, lon2):
	radius = 6371000
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dphi = p2 - p1
	dlmb = math.radians(lon2 - lon1)
	a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
	return 2 * radius * math.asin(math.sqrt(a))


def _check_geofence(employee, lat, lng, now):
	"""Returns (distance in metres or None, outside_radius flag)."""
	mode = str(_conf("geofence_mode", "block")).lower()
	if mode == "off" or lat is None:
		return None, False

	location = _get_shift_location(_get_shift_type(employee, getdate(now)))
	if not location:
		return None, False

	distance = _distance_m(lat, lng, flt(location.latitude), flt(location.longitude))
	outside = distance > flt(location.checkin_radius)
	if outside and mode == "block":
		frappe.throw(
			_("You are {0} m from your work location. Check-in is allowed within {1} m.").format(
				round(distance), round(flt(location.checkin_radius))
			)
		)
	return round(distance, 1), outside


def _reference_photo(employee):
	if not employee.image:
		return None
	name = frappe.db.get_value("File", {"file_url": employee.image}, "name")
	if not name:
		return None
	try:
		return frappe.get_doc("File", name).get_content()
	except Exception:
		return None


def _match_face(employee, live_bytes):
	"""Returns (status, score). Never blocks the check-in: provider problems end up as Review."""
	provider = str(_conf("match_provider", "none")).lower()
	if provider == "none":
		return "Not Checked", None

	reference = _reference_photo(employee)
	if not reference:
		return "Review", None

	try:
		if provider == "aws":
			score = _score_aws(reference, live_bytes)
		else:
			frappe.throw(_("Unknown match provider {0}").format(provider))
	except Exception:
		frappe.log_error(title="Face Checkin: match failed")
		return "Review", None

	if score >= flt(_conf("match_threshold", 90)):
		return "Matched", score
	if score >= flt(_conf("review_threshold", 70)):
		return "Review", score
	return "Failed", score


def _score_aws(reference, live):
	import boto3  # add boto3 to pyproject dependencies before using this provider

	client = boto3.client(
		"rekognition",
		region_name=_conf("aws_region", "ap-south-1"),
		aws_access_key_id=_conf("aws_key"),
		aws_secret_access_key=_conf("aws_secret"),
	)
	response = client.compare_faces(
		SourceImage={"Bytes": reference}, TargetImage={"Bytes": live}, SimilarityThreshold=0
	)
	matches = response.get("FaceMatches") or []
	return max((m["Similarity"] for m in matches), default=0.0)
