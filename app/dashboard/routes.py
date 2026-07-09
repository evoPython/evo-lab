from flask import (
    Blueprint,
    render_template,
    make_response,
    current_app,
    request,
    jsonify,
    abort,
)

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


@dashboard.route("/pair")
def pair():
    """
    Visit /dashboard/pair?key=<DEVICE_TOKEN> from a trusted device to
    pair it. Meant to be reached via a private link or QR code you
    generate for yourself, not something exposed publicly.
    """

    expected = current_app.config.get("DEVICE_TOKEN")
    key = request.args.get("key", "")

    if not expected or key != expected:
        abort(403)

    response = make_response(
        "Device successfully paired. You can close this page."
    )

    response.set_cookie(
        "evo_device",
        expected,
        httponly=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 365,  # 1 year
    )

    return response


@dashboard.route("/unpair")
def unpair():

    response = make_response("Device unpaired.")
    response.delete_cookie("evo_device")

    return response


@dashboard.route("/api/stats")
@require_personal_device
def api_stats():
    return jsonify(get_system_stats())
