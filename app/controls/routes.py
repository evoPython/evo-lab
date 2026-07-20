from flask import Blueprint, render_template, jsonify

from app.core.security import require_personal_device
from app.core.notify import notify
from app.controls import actions, volume, brightness, media_keys


controls = Blueprint("controls", __name__, url_prefix="/controls")


@controls.route("/")
@require_personal_device
def index():
    return render_template("controls.html")


@controls.route("/lock", methods=["POST"])
@require_personal_device
def lock():
    return _perform(actions.lock_screen, "Screen locked")


@controls.route("/sleep", methods=["POST"])
@require_personal_device
def sleep():
    return _perform(actions.suspend, "Suspending")


@controls.route("/restart", methods=["POST"])
@require_personal_device
def restart():
    return _perform(actions.restart, "Restarting")


@controls.route("/shutdown", methods=["POST"])
@require_personal_device
def shutdown():
    return _perform(actions.shutdown, "Shutting down")


@controls.route("/volume/status")
@require_personal_device
def volume_status():
    try:
        return jsonify(volume.get_status())
    except volume.VolumeError as exc:
        return jsonify({"error": str(exc)}), 500


@controls.route("/volume/up", methods=["POST"])
@require_personal_device
def volume_up():
    return _perform(volume.volume_up, "Volume up", err_cls=volume.VolumeError)


@controls.route("/volume/down", methods=["POST"])
@require_personal_device
def volume_down():
    return _perform(volume.volume_down, "Volume down", err_cls=volume.VolumeError)


@controls.route("/volume/mute", methods=["POST"])
@require_personal_device
def volume_mute():
    return _perform(volume.toggle_mute, "Mute toggled", err_cls=volume.VolumeError)


@controls.route("/brightness/status")
@require_personal_device
def brightness_status():
    try:
        return jsonify(brightness.get_status())
    except brightness.BrightnessError as exc:
        return jsonify({"error": str(exc)}), 500


@controls.route("/brightness/up", methods=["POST"])
@require_personal_device
def brightness_up():
    return _perform(brightness.brightness_up, "Brightness up", err_cls=brightness.BrightnessError)


@controls.route("/brightness/down", methods=["POST"])
@require_personal_device
def brightness_down():
    return _perform(brightness.brightness_down, "Brightness down", err_cls=brightness.BrightnessError)


@controls.route("/media/status")
@require_personal_device
def media_status():
    try:
        return jsonify(media_keys.get_status())
    except media_keys.MediaKeyError as exc:
        return jsonify({"error": str(exc)}), 500


@controls.route("/media/playpause", methods=["POST"])
@require_personal_device
def media_playpause():
    return _perform(media_keys.play_pause, None, err_cls=media_keys.MediaKeyError)


@controls.route("/media/next", methods=["POST"])
@require_personal_device
def media_next():
    return _perform(media_keys.next_track, None, err_cls=media_keys.MediaKeyError)


@controls.route("/media/prev", methods=["POST"])
@require_personal_device
def media_prev():
    return _perform(media_keys.prev_track, None, err_cls=media_keys.MediaKeyError)


def _perform(action_fn, notify_msg=None, err_cls=actions.ActionError):
    try:
        action_fn()
        if notify_msg:
            notify("Remote", notify_msg)
        return jsonify({"status": "ok"})
    except err_cls as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
