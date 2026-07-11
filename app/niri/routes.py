import os
import shutil
import subprocess
import tempfile

from flask import Blueprint, render_template, jsonify, request, send_file

from app.core.security import require_personal_device
from app.core.notify import notify
from app.niri import client


niri = Blueprint("niri", __name__, url_prefix="/niri")

SCREENSHOT_PATH = os.path.join(tempfile.gettempdir(), "evo_niri_screenshot.png")


@niri.route("/")
@require_personal_device
def index():
    return render_template("niri.html")


@niri.route("/api/state")
@require_personal_device
def api_state():
    try:
        return jsonify(client.get_state())
    except client.NiriError as exc:
        return jsonify({"error": str(exc)}), 500


@niri.route("/api/action", methods=["POST"])
@require_personal_device
def api_action():
    data = request.get_json(silent=True) or {}
    try:
        client.run_action(
            data.get("action"),
            window_id=data.get("window_id"),
            workspace_idx=data.get("workspace_idx"),
            value=data.get("value"),
        )
        notify("Remote", f"Niri: {data.get('action')}")
        return jsonify({"status": "ok"})
    except (client.NiriError, TypeError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@niri.route("/screenshot")
@require_personal_device
def screenshot():
    if shutil.which("grim") is None:
        return jsonify({"error": "grim not found"}), 500
    try:
        subprocess.run(
            ["grim", SCREENSHOT_PATH],
            check=True, timeout=5, capture_output=True,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return send_file(SCREENSHOT_PATH, mimetype="image/png")
