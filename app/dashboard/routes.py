from flask import Blueprint, render_template
from .system import get_system_stats


dashboard = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard"
)


@dashboard.route("/")
def index():

    stats = get_system_stats()

    return render_template(
        "dashboard.html",
        stats=stats
    )
