import shutil
import time

from flask import Blueprint, jsonify, request, Response

from app.core.security import require_personal_device
from app.core.notify import notify
from app.media import stream, laptop_stream
from app.niri import client as niri_client


media = Blueprint("media", __name__, url_prefix="/media")


@media.route("/stream/mjpeg")
def stream_mjpeg():
    # Fetched by mpv running locally on the laptop, not by the phone,
    # so it isn't gated behind require_personal_device (mpv doesn't
    # send the pairing cookie). It only ever serves whatever frame
    # the paired device most recently pushed.
    return Response(
        stream.mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@media.route("/stream/frame", methods=["POST"])
@require_personal_device
def stream_frame():
    try:
        stream.set_frame(request.get_data())
        return jsonify({"status": "ok"})
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/stream/camera/start", methods=["POST"])
@require_personal_device
def camera_start():
    mjpeg_url = request.host_url.rstrip("/") + "/media/stream/mjpeg"
    try:
        stream.camera_start(mjpeg_url)
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    # Give the mpv window a moment to appear, then focus it.
    focused = False
    for _ in range(10):
        time.sleep(0.3)
        try:
            windows = niri_client.get_windows()
        except niri_client.NiriError:
            continue
        match = next((w for w in windows if stream.WINDOW_TITLE in (w.get("title") or "")), None)
        if match:
            try:
                niri_client.run_action("focus-window", window_id=match["id"])
                focused = True
            except niri_client.NiriError:
                pass
            break

    notify("Remote", "Camera stream started")
    return jsonify({"status": "ok", "focused": focused})


@media.route("/stream/camera/stop", methods=["POST"])
@require_personal_device
def camera_stop():
    stream.camera_stop()
    notify("Remote", "Camera stream stopped")
    return jsonify({"status": "ok"})


@media.route("/stream/audio/start", methods=["POST"])
@require_personal_device
def audio_start():
    try:
        stream.audio_start()
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    notify("Remote", "Mic stream started")
    return jsonify({"status": "ok"})


@media.route("/stream/audio/chunk", methods=["POST"])
@require_personal_device
def audio_chunk():
    try:
        stream.audio_write(request.get_data())
        return jsonify({"status": "ok"})
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/stream/audio/stop", methods=["POST"])
@require_personal_device
def audio_stop():
    stream.audio_stop()
    notify("Remote", "Mic stream stopped")
    return jsonify({"status": "ok"})


# --- Laptop -> phone: view/hear the laptop's own camera and mic ---

@media.route("/laptop/camera/stream")
@require_personal_device
def laptop_camera_stream():
    if not shutil.which("ffmpeg"):
        return jsonify({"error": "ffmpeg not found"}), 500
    return Response(
        laptop_stream.camera_generator(),
        mimetype="multipart/x-mixed-replace; boundary=ffmpeg",
    )


@media.route("/laptop/camera/stop", methods=["POST"])
@require_personal_device
def laptop_camera_stop():
    laptop_stream.camera_stop()
    notify("Remote", "Laptop camera stopped")
    return jsonify({"status": "ok"})


@media.route("/laptop/mic/stream")
@require_personal_device
def laptop_mic_stream():
    if not shutil.which("ffmpeg"):
        return jsonify({"error": "ffmpeg not found"}), 500
    return Response(laptop_stream.mic_generator(), mimetype="audio/mpeg")


@media.route("/laptop/mic/stop", methods=["POST"])
@require_personal_device
def laptop_mic_stop():
    laptop_stream.mic_stop()
    notify("Remote", "Laptop mic stopped")
    return jsonify({"status": "ok"})
