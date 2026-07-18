from flask import Blueprint, jsonify, request

from app.core.security import require_personal_device
from app.modes import service


modes = Blueprint("modes", __name__, url_prefix="/modes")


@modes.route("/api/state")
@require_personal_device
def api_state():
    return jsonify({
        "mode": service.get_mode(),
        "changed_at": service.get_mode_changed_at(),
        "modes": list(service.MODES),
    })


@modes.route("/api/set", methods=["POST"])
@require_personal_device
def api_set():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")

    if mode not in service.MODES:
        return jsonify({"status": "error", "message": "unknown mode"}), 400

    try:
        warnings = service.set_mode(mode)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ok", "mode": mode, "warnings": warnings})
