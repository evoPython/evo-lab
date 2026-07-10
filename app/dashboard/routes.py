from flask import Blueprint, render_template, jsonify

from app.core.security import is_personal_device, require_personal_device
from app.dashboard.system import get_system_stats


dashboard = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard"
)


@dashboard.route("/")
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
