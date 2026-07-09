from flask import Blueprint, render_template, jsonify

from app.core.security import require_personal_device
from app.controls import actions


controls = Blueprint(
    "controls",
    __name__,
    url_prefix="/controls"
)


@controls.route("/")
@require_personal_device
def index():
    return render_template("controls.html")


@controls.route("/lock", methods=["POST"])
@require_personal_device
def lock():
    return _perform(actions.lock_screen)


@controls.route("/sleep", methods=["POST"])
@require_personal_device
def sleep():
    return _perform(actions.suspend)


@controls.route("/restart", methods=["POST"])
@require_personal_device
def restart():
    return _perform(actions.restart)


@controls.route("/shutdown", methods=["POST"])
@require_personal_device
def shutdown():
    return _perform(actions.shutdown)


def _perform(action_fn):
    try:
        action_fn()
        return jsonify({"status": "ok"})
    except actions.ActionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
