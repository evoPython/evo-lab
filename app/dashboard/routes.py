from flask import Blueprint, render_template, jsonify, request

from app.core.security import is_personal_device, require_personal_device
from app.dashboard.system import get_system_stats
from app.dashboard.battery_history import get_history as get_battery_history
from app.modes.service import get_mode


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
    IPs, core counts, or temperatures here.

    Battery percent/charging is the one deliberate exception: it's
    surfaced on the public "server" tab as a small history chip.
    secsleft (time remaining) stays behind auth along with the rest
    of /api/stats.
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
        "battery": (
            {"percent": stats["battery"]["percent"], "charging": stats["battery"]["charging"]}
            if stats["battery"] else None
        ),
        "net_sent_bps": stats["network"]["sent_rate_bps"],
        "net_recv_bps": stats["network"]["recv_rate_bps"],
        "processes": stats["processes"],
        "uptime": stats["uptime"],
        # Just the mode name — no detail about *why* it's in that mode,
        # what units it stopped, battery thresholds, etc. Those stay
        # behind /modes/api/state (auth-gated). This is what drives the
        # read-only "power mode" indicator on the public server tab.
        "mode": get_mode(),
    })


@dashboard.route("/api/battery-history")
def api_battery_history():
    """
    Public, unauthenticated — same trust level as /api/public-stats.
    Backs the battery history chip on the homepage "server" tab.

    `hours` accepts fractions (0.5 for the 30m range). Resolution
    scales down as the window grows so the payload stays small: the
    30m/1h views get ~1 point per logged minute, the 1d view buckets
    to ~15 minutes, the 1w view buckets to ~1 hour.
    """
    hours = request.args.get("hours", default=1, type=float)
    hours = max(1 / 60, min(hours, 24 * 7))

    if hours <= 1:
        max_points = 60
    elif hours <= 24:
        max_points = 96
    else:
        max_points = 168

    return jsonify(get_battery_history(hours=hours, max_points=max_points))
