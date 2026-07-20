import json
import time
import uuid

from flask import has_request_context, session

MAX_LOGS = 80
MAX_LOG_BODY_CHARS = 6000
SENSITIVE_KEYS = {"password", "token", "authorization", "x-token", "admin-token"}

_log_store = {}


def _log_key():
    if not has_request_context():
        return None
    return session.get("auth_id")


def debug_enabled():
    if not has_request_context():
        return False

    auth_id = session.get("auth_id")
    if auth_id:
        from services.auth_store import get_auth_session

        row = get_auth_session(auth_id)
        if row:
            return bool(row.get("debug_mode"))

    return bool(session.get("debug_mode"))


def _redact_value(key, value):
    key_lower = key.lower()
    if key_lower == "password":
        return "***REDACTED***"
    if key_lower in SENSITIVE_KEYS and value:
        text = str(value)
        if len(text) <= 8:
            return "***"
        return f"{text[:6]}…{text[-4:]}"
    return value


def _redact_mapping(mapping):
    if not isinstance(mapping, dict):
        return mapping
    return {key: _redact_value(key, value) for key, value in mapping.items()}


def _truncate_for_log(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            encoded = json.dumps(value)
        except (TypeError, ValueError):
            encoded = str(value)
        if len(encoded) <= MAX_LOG_BODY_CHARS:
            return value
        return {
            "_truncated": True,
            "bytes": len(encoded),
            "preview": encoded[:MAX_LOG_BODY_CHARS] + "…",
        }
    text = str(value)
    if len(text) <= MAX_LOG_BODY_CHARS:
        return text
    return text[:MAX_LOG_BODY_CHARS] + "…"


def _safe_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return str(value)


def log_http_exchange(
    *,
    method,
    url,
    request_headers=None,
    params=None,
    json_body=None,
    response_status=None,
    response_headers=None,
    response_body=None,
    duration_ms=None,
    error=None,
    label=None,
    force=False,
):
    if not debug_enabled() and not force:
        return None

    entry = {
        "id": uuid.uuid4().hex[:10],
        "ts": time.time(),
        "label": label or f"{method} {url.split('/core/api/')[-1]}",
        "method": method,
        "url": url,
        "params": params or {},
        "request_headers": _redact_mapping(request_headers or {}),
        "request_body": _truncate_for_log(json_body),
        "response_status": response_status,
        "response_headers": dict(response_headers or {}),
        "response_body": _truncate_for_log(_safe_json(response_body)),
        "duration_ms": duration_ms,
        "error": error,
        "kind": "http",
    }

    _append_log(entry)
    return entry["id"]


def log_debug_event(label, data, *, force=False):
    if not debug_enabled() and not force:
        return None

    entry = {
        "id": uuid.uuid4().hex[:10],
        "ts": time.time(),
        "label": label,
        "method": "DEBUG",
        "url": "",
        "params": {},
        "request_headers": {},
        "request_body": _truncate_for_log(data),
        "response_status": None,
        "response_headers": {},
        "response_body": None,
        "duration_ms": None,
        "error": None,
        "kind": "event",
    }

    _append_log(entry)
    return entry["id"]


def _append_log(entry):
    key = _log_key()
    if not key:
        return

    logs = list(_log_store.get(key, []))
    logs.append(entry)
    _log_store[key] = logs[-MAX_LOGS:]


def get_debug_logs():
    if not has_request_context():
        return []

    key = _log_key()
    if not key:
        return []

    return list(_log_store.get(key, []))


def clear_debug_logs():
    if not has_request_context():
        return

    key = _log_key()
    if key:
        _log_store[key] = []


def clear_logs_for_session(auth_id):
    if auth_id:
        _log_store.pop(auth_id, None)
