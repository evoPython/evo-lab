from flask import Blueprint, jsonify, request

from app.core.security import require_personal_device
from app.network import nm, monitor

network = Blueprint("network", __name__, url_prefix="/network")


@network.route("/status")
@require_personal_device
def status():
    try:
        data = nm.get_status()
    except nm.NMError as exc:
        return jsonify({"error": str(exc)}), 500
    data["auto_enabled"] = monitor.auto_enabled
    data["hotspot_ssid"] = nm.get_hotspot_ssid() or monitor.HOTSPOT_SSID
    data["priority_ssid"] = monitor.PRIORITY_SSID
    return jsonify(data)


@network.route("/scan")
@require_personal_device
def scan():
    try:
        return jsonify({"networks": nm.scan_networks()})
    except nm.NMError as exc:
        return jsonify({"error": str(exc)}), 500


@network.route("/connect", methods=["POST"])
@require_personal_device
def connect():
    body = request.get_json(silent=True) or {}
    ssid = body.get("ssid")
    password = body.get("password") or None
    if not ssid:
        return jsonify({"status": "error", "message": "ssid required"}), 400
    try:
        with monitor.action_lock:
            nm.connect(ssid, password)
        return jsonify({"status": "ok"})
    except nm.NMError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@network.route("/connect/priority", methods=["POST"])
@require_personal_device
def connect_priority():
    """
    Drop the hotspot, actively retry the known priority network (pisay2, no
    password prompt needed since we already have it saved), and restore the
    hotspot if that didn't work out.
    """
    try:
        with monitor.action_lock:
            status = nm.reconnect_priority(
                monitor.HOTSPOT_SSID,
                priority_ssid=monitor.PRIORITY_SSID,
                priority_password=monitor.PRIORITY_PASSWORD,
                wait_seconds=8,
            )
        return jsonify({"status": "ok", **status})
    except nm.NMError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@network.route("/disconnect", methods=["POST"])
@require_personal_device
def disconnect():
    try:
        with monitor.action_lock:
            nm.disconnect()
        return jsonify({"status": "ok"})
    except nm.NMError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@network.route("/hotspot/on", methods=["POST"])
@require_personal_device
def hotspot_on():
    try:
        with monitor.action_lock:
            nm.hotspot_up(monitor.HOTSPOT_SSID)
        return jsonify({"status": "ok"})
    except nm.NMError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@network.route("/hotspot/off", methods=["POST"])
@require_personal_device
def hotspot_off():
    try:
        with monitor.action_lock:
            nm.hotspot_down()
        return jsonify({"status": "ok"})
    except nm.NMError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@network.route("/auto", methods=["POST"])
@require_personal_device
def auto():
    body = request.get_json(silent=True) or {}
    monitor.set_auto(bool(body.get("enabled", True)))
    return jsonify({"status": "ok", "auto_enabled": monitor.auto_enabled})
