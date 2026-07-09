from flask import (
    Blueprint,
    render_template,
    make_response,
    current_app
)

from app.core.security import is_personal_device


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
# ------------------------------------------------ 
# UNCOMMENT AND CONNECT TO /dashboard/pair TO PAIR 
# ------------------------------------------------
# @dashboard.route("/pair")
# def pair():
#
#     response = make_response(
#         """
#         Device successfully paired.
#         You can close this page.
#         """
#     )
#
#     response.set_cookie(
#         "evo_device",
#         current_app.config["DEVICE_TOKEN"],
#         httponly=True,
#         samesite="Lax"
#     )
#
#     return response
