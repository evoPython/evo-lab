from flask import Blueprint, jsonify, request

from app.core.security import require_personal_device
from app.core.notify import notify
from app.launcher import apps


launcher = Blueprint("launcher", __name__, url_prefix="/launcher")


@launcher.route("/api/apps")
@require_personal_device
def api_apps():
    return jsonify(apps.list_apps())


@launcher.route("/api/launch", methods=["POST"])
@require_personal_device
def api_launch():
    data = request.get_json(silent=True) or {}
    try:
        name = apps.launch(data.get("id"))
        notify("Remote", f"Launched {name}")
        return jsonify({"status": "ok", "name": name})
    except (ValueError, OSError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
