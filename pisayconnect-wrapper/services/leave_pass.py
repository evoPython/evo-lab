import copy
import json
from datetime import datetime
from pathlib import Path

from services.request_log import log_debug_event

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_leavepass_request.json"
_SAMPLE_SCHEMA = None


DEPARTURE_FROM_HOME_FIELDS = (
    "DepartureDateTimeFromHome",
    "DepartureDateTimeFromHomeStrInfo",
    "DepartureDateTimeFromHomeStr",
    "DepartureDateTimeFromHomeStrVal",
)

ARRIVAL_FIELDS = (
    "ArrivalDateTime",
    "ArrivalDateTimeStrInfo",
)

GUARDIAN_SIGNATURE_USER_FIELDS = (
    "UserId",
    "UserName",
    "Password",
    "IsActive",
    "EmployeeId",
    "StudentId",
    "IsStudent",
    "UserAvatar",
    "SignatureId",
    "Signature",
    "IsSMSNotificationAllowed",
    "NotificationList",
    "FailedLoginCount",
)

GUARDIAN_SIGNATURE_FIELDS = (
    "AttachGuardianSignatureModifiedBy",
    "AttachGuardianSignatureModifiedById",
    "IsAttachGuardianSignature",
    "DateAttachGuardianSignatureModified",
    "CompanionName",
    "ContactNo",
    "Relationship",
)


def _load_sample_schema():
    with SAMPLE_PATH.open() as f:
        sample = json.load(f)
    return {
        "leave_pass": list(sample.keys()),
        "student": list(sample["Student"].keys()),
        "guardian_user": list(sample["AttachGuardianSignatureModifiedBy"].keys()),
        "signature": list(sample["AttachGuardianSignatureModifiedBy"]["Signature"].keys()),
        "student_user": list(sample["Student"]["User"].keys()),
        "residence_head": list(sample["ResidenceHeadApprovalModifiedBy"].keys()),
    }


def get_sample_schema():
    global _SAMPLE_SCHEMA
    if _SAMPLE_SCHEMA is None:
        _SAMPLE_SCHEMA = _load_sample_schema()
    return _SAMPLE_SCHEMA


def _pick_keys(source, keys):
    if not isinstance(source, dict):
        return source
    return {key: source[key] for key in keys if key in source}


def _slim_signature(signature, schema):
    if not isinstance(signature, dict):
        return signature
    return _pick_keys(signature, schema["signature"])


def _slim_guardian_user(guardian_user, schema):
    slim = _pick_keys(guardian_user, schema["guardian_user"])
    if isinstance(slim.get("Signature"), dict):
        slim["Signature"] = _slim_signature(slim["Signature"], schema)
    return slim


def _slim_student_user(user, schema):
    slim = _pick_keys(user, schema["student_user"])
    if isinstance(slim.get("Signature"), dict):
        slim["Signature"] = _slim_signature(slim["Signature"], schema)
    return slim


def unwrap_leave_pass_response(data):
    """Unwrap GET /studentLeavePass/{id} responses to the pass dict."""
    if not isinstance(data, dict):
        return {}

    if data.get("StudentLeavePassId") is not None:
        return data

    for key in ("StudentLeavePass", "Data", "Result"):
        nested = data.get(key)
        if isinstance(nested, dict) and nested.get("StudentLeavePassId") is not None:
            return nested

    return data


def slim_leave_pass_for_update(raw_pass):
    """Keep only fields present in sample_leavepass_request.json."""
    schema = get_sample_schema()
    payload = _pick_keys(raw_pass, schema["leave_pass"])

    student_src = raw_pass.get("Student")
    if isinstance(student_src, dict):
        student = _pick_keys(student_src, schema["student"])
        if isinstance(student.get("GuardianUser"), dict):
            student["GuardianUser"] = _slim_guardian_user(student["GuardianUser"], schema)
        if isinstance(student.get("User"), dict):
            student["User"] = _slim_student_user(student["User"], schema)
        payload["Student"] = student

    if isinstance(payload.get("AttachGuardianSignatureModifiedBy"), dict):
        payload["AttachGuardianSignatureModifiedBy"] = _slim_guardian_user(
            payload["AttachGuardianSignatureModifiedBy"],
            schema,
        )

    if isinstance(payload.get("ResidenceHeadApprovalModifiedBy"), dict):
        payload["ResidenceHeadApprovalModifiedBy"] = _pick_keys(
            payload["ResidenceHeadApprovalModifiedBy"],
            schema["residence_head"],
        )

    return payload


def _summarize_guardian_fields(payload):
    guardian = payload.get("AttachGuardianSignatureModifiedBy") or {}
    signature = guardian.get("Signature") or {}
    return {
        "AttachGuardianSignatureModifiedById": payload.get("AttachGuardianSignatureModifiedById"),
        "IsAttachGuardianSignature": payload.get("IsAttachGuardianSignature"),
        "DateAttachGuardianSignatureModified": payload.get("DateAttachGuardianSignatureModified"),
        "CompanionName": payload.get("CompanionName"),
        "ContactNo": payload.get("ContactNo"),
        "Relationship": payload.get("Relationship"),
        "guardian_user_id": guardian.get("UserId"),
        "signature_id": guardian.get("SignatureId"),
        "signature_file_id": signature.get("FileId"),
        "student_guardian_signature_file_id": (
            ((payload.get("Student") or {}).get("GuardianUser") or {}).get("Signature") or {}
        ).get("FileId"),
    }


def parse_departure_input(value):
    """Parse datetime-local or ISO-ish string from the approve form."""
    text = (value or "").strip()
    if not text:
        raise ValueError("Departure date and time is required.")

    for fmt in (
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(f"Invalid departure date/time: {text}") from exc


def format_departure_from_home(dt):
    return {
        "DepartureDateTimeFromHome": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "DepartureDateTimeFromHomeStrInfo": dt.strftime("%B %d, %Y %I:%M %p"),
        "DepartureDateTimeFromHomeStr": dt.strftime("%B %d, %Y"),
        "DepartureDateTimeFromHomeStrVal": dt.strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_arrival_str_info(dt):
    return dt.strftime("%B %d, %Y %I:%M %p")


def preserve_arrival_fields(payload, raw_pass):
    """Carry campus arrival timestamps from the fetched pass into the update payload."""
    arrival = raw_pass.get("ArrivalDateTime")
    arrival_info = (raw_pass.get("ArrivalDateTimeStrInfo") or "").strip()

    if arrival:
        payload["ArrivalDateTime"] = arrival
    if arrival_info:
        payload["ArrivalDateTimeStrInfo"] = arrival_info
    elif arrival:
        try:
            dt = datetime.fromisoformat(str(arrival).replace("Z", "+00:00")).replace(tzinfo=None)
            payload["ArrivalDateTimeStrInfo"] = format_arrival_str_info(dt)
        except ValueError:
            pass

    return payload


def format_guardian_signature_modified(dt=None):
    when = dt or datetime.now()
    return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 10000:02d}"


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _has_signature(signature):
    if not signature or not isinstance(signature, dict):
        return False
    return bool(signature.get("FileId") or signature.get("Token") or signature.get("FileName"))


def normalize_user_info(data):
    """Unwrap /user/info responses to the user object that carries Signature."""
    if not isinstance(data, dict):
        return {}

    if data.get("UserId") is not None:
        return data

    for key in ("Data", "User", "Result"):
        nested = data.get(key)
        if isinstance(nested, dict) and nested.get("UserId") is not None:
            return nested

    return data


def _guardian_user_from_pass(raw_pass):
    student = raw_pass.get("Student") or {}
    guardian = raw_pass.get("AttachGuardianSignatureModifiedBy")
    if guardian and isinstance(guardian, dict) and not _is_blank(guardian):
        return guardian
    guardian = student.get("GuardianUser")
    if guardian and isinstance(guardian, dict) and not _is_blank(guardian):
        return guardian
    return {}


def is_pending_return_signature(raw_pass):
    """True when parent approval is still required (departure or guardian fields missing)."""
    if not raw_pass:
        return True

    if _is_blank(raw_pass.get("DepartureDateTimeFromHomeStrInfo")):
        return True

    guardian = _guardian_user_from_pass(raw_pass)
    if not guardian:
        return True

    if not _has_signature(guardian.get("Signature")):
        return True

    if _is_blank(raw_pass.get("AttachGuardianSignatureModifiedById")):
        return True

    if _is_blank(raw_pass.get("IsAttachGuardianSignature")):
        return True

    if _is_blank(raw_pass.get("CompanionName")):
        return True

    if _is_blank(raw_pass.get("ContactNo")):
        return True

    if _is_blank(raw_pass.get("Relationship")):
        return True

    return False


def build_attach_guardian_signature_user(parent_user_info, student_guardian_user=None):
    """Build AttachGuardianSignatureModifiedBy from parent GET /user/info (+ student fallback)."""
    info = normalize_user_info(parent_user_info)
    if not info:
        raise ValueError("Could not load parent user info from PisayConnect.")

    result = copy.deepcopy(student_guardian_user or {})

    for key in GUARDIAN_SIGNATURE_USER_FIELDS:
        if key in ("SignatureId", "Signature"):
            continue
        if key in info and info[key] is not None:
            result[key] = copy.deepcopy(info[key]) if isinstance(info[key], dict) else info[key]
        elif key not in result and student_guardian_user and student_guardian_user.get(key) is not None:
            value = student_guardian_user[key]
            result[key] = copy.deepcopy(value) if isinstance(value, dict) else value

    signature = info.get("Signature")
    if signature and isinstance(signature, dict):
        result["Signature"] = copy.deepcopy(signature)
    if info.get("SignatureId") is not None:
        result["SignatureId"] = info["SignatureId"]
    elif result.get("Signature") and result["Signature"].get("FileId"):
        result["SignatureId"] = result["Signature"]["FileId"]

    if not _has_signature(result.get("Signature")):
        raise ValueError("Parent account has no signature on file in PisayConnect.")

    if not result.get("UserId"):
        raise ValueError("Could not resolve parent user id for guardian signature.")

    return result


def format_companion_name(student):
    """Match PisayConnect format, e.g. Joel M. Cabrera from father name fields."""
    first = (student.get("FatherFirstName") or "").strip()
    middle = (student.get("FatherMiddleName") or "").strip()
    last = (student.get("FatherLastName") or "").strip()

    if not first and not middle and not last:
        return ""

    parts = []
    if first:
        parts.append(first.title())
    if middle:
        middle_part = middle.rstrip(".")
        parts.append(f"{middle_part.title()}.")
    if last:
        parts.append(last.title())

    return " ".join(parts)


def apply_guardian_signature_fields(payload, parent_user_info):
    student = payload.get("Student") or {}
    guardian_user = build_attach_guardian_signature_user(
        parent_user_info,
        student.get("GuardianUser"),
    )

    payload["AttachGuardianSignatureModifiedBy"] = guardian_user
    payload["AttachGuardianSignatureModifiedById"] = guardian_user.get("UserId")
    payload["IsAttachGuardianSignature"] = True
    payload["DateAttachGuardianSignatureModified"] = format_guardian_signature_modified()

    if payload.get("Student") is not None:
        payload["Student"] = dict(payload["Student"])
        payload["Student"]["GuardianUser"] = copy.deepcopy(guardian_user)
        if guardian_user.get("UserId"):
            payload["Student"]["GuardianUserId"] = guardian_user["UserId"]

    companion = (payload.get("CompanionName") or "").strip() or format_companion_name(student)
    if companion:
        payload["CompanionName"] = companion

    contact = (payload.get("ContactNo") or "").strip() or (student.get("MobileNo") or "").strip()
    if contact:
        payload["ContactNo"] = contact

    payload["Relationship"] = (payload.get("Relationship") or "").strip() or "parent"

    return payload


def build_approve_return_payload(raw_pass, departure_dt, parent_user_info=None):
    """Build an update payload matching sample_leavepass_request.json shape."""
    payload = copy.deepcopy(slim_leave_pass_for_update(raw_pass))
    before = {field: payload.get(field) for field in DEPARTURE_FROM_HOME_FIELDS}
    payload.update(format_departure_from_home(departure_dt))
    after = {field: payload.get(field) for field in DEPARTURE_FROM_HOME_FIELDS}

    arrival_before = {field: payload.get(field) for field in ARRIVAL_FIELDS}
    preserve_arrival_fields(payload, raw_pass)
    arrival_after = {field: payload.get(field) for field in ARRIVAL_FIELDS}

    guardian_before = _summarize_guardian_fields(payload)
    apply_guardian_signature_fields(payload, parent_user_info)
    guardian_after = _summarize_guardian_fields(payload)

    try:
        payload_bytes = len(json.dumps(payload))
    except (TypeError, ValueError):
        payload_bytes = None

    log_debug_event(
        "approve-return/build-payload",
        {
            "pass_id": payload.get("StudentLeavePassId"),
            "departure_input_parsed": departure_dt.isoformat(),
            "departure_fields_before": before,
            "departure_fields_after": after,
            "arrival_fields_before": arrival_before,
            "arrival_fields_after": arrival_after,
            "guardian_fields_before": guardian_before,
            "guardian_fields_after": guardian_after,
            "payload_bytes": payload_bytes,
            "top_level_keys": sorted(payload.keys()),
        },
        force=True,
    )

    return payload
