# Face Checkin

Employee check-in page for Frappe HR. Each employee signs in on their own phone, opens `/checkin`,
and the page captures a selfie and the GPS location. The server saves an Employee Checkin with the photo
and location, optionally checks the location against the shift location, and optionally compares the
selfie with the photo in the Employee record.

Optional site config keys (all start with `face_checkin_`):

| Key | Default | Meaning |
|---|---|---|
| require_location | 1 | Reject a check-in that has no location |
| max_accuracy_m | 150 | Reject a location whose reported accuracy is worse than this many metres (0 = off) |
| geofence_mode | block | block, flag or off. Only applies when the employee's shift has a shift location |
| match_provider | none | none or aws |
| match_threshold | 90 | Similarity at or above this is Matched |
| review_threshold | 70 | Similarity at or above this (and below match_threshold) is Review, lower is Failed |
| hold_unmatched | 1 | Tick Skip Auto Attendance on Review and Failed punches so HR can review them first |
| aws_region, aws_key, aws_secret | | Needed only for match_provider = aws (also add boto3 to pyproject dependencies) |
