from flask import Blueprint, render_template, jsonify

from app.core.security import is_personal_device, require_personal_device
from app.dashboard.system import get_system_stats


dashboard = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard"
)


@dashboard.route("/")
@require_personal_device
def index():

    personal = is_personal_device()

    return render_template(
        "dashboard.html",
        personal=personal
    )


@dashboard.route("/api/stats")
@require_personal_device
def api_stats():
    return jsonify(get_system_stats())


@dashboard.route("/api/public-stats")
def api_public_stats():
    """
    Trimmed-down, unauthenticated version of /api/stats for the
    homepage "server" tab. Only exposes load percentages and uptime —
    no IPs, core counts, temperatures, or battery details.
    """
    stats = get_system_stats()
    return jsonify({
        "cpu": stats["cpu"]["percent"],
        "ram": stats["ram"]["percent"],
        "disk": stats["disk"]["percent"],
        "uptime": stats["uptime"],
    })
