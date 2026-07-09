from flask import request
from flask import current_app


def is_personal_device():

    token = request.cookies.get(
        "evo_device"
    )

    return token == current_app.config["DEVICE_TOKEN"]
