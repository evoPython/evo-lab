from flask import Blueprint, render_template

from app.core.security import require_personal_device


remote = Blueprint("remote", __name__, url_prefix="/remote")


@remote.route("/")
@require_personal_device
def index():
    return render_template("remote.html")
