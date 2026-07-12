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
    homepage "server" tab. Sized/aggregate numbers are fine to show
    publicly — it's identifying details that stay behind auth: no
    IPs, core counts, temperatures, or battery details here.
    """
    stats = get_system_stats()
    return jsonify({
        "cpu": stats["cpu"]["percent"],
        "load": stats["load"],
        "ram": stats["ram"]["percent"],
        "ram_used_gb": stats["ram"]["used_gb"],
        "ram_total_gb": stats["ram"]["total_gb"],
        "swap": stats["swap"]["percent"],
        "swap_used_gb": stats["swap"]["used_gb"],
        "swap_total_gb": stats["swap"]["total_gb"],
        "disk": stats["disk"]["percent"],
        "disk_used_gb": stats["disk"]["used_gb"],
        "disk_total_gb": stats["disk"]["total_gb"],
        "net_sent_bps": stats["network"]["sent_rate_bps"],
        "net_recv_bps": stats["network"]["recv_rate_bps"],
        "processes": stats["processes"],
        "uptime": stats["uptime"],
    })
