from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    send_from_directory,
)

from app.core.security import require_personal_device
from app.core.notify import notify
from app.tools import url_opener, clipboard, files


tools = Blueprint(
    "tools",
    __name__,
    url_prefix="/tools"
)


@tools.route("/")
@require_personal_device
def index():
    return render_template("tools.html")


# ---------------------------------------------------------------
# URL opener
# ---------------------------------------------------------------

@tools.route("/open-url", methods=["GET", "POST"])
@require_personal_device
def open_url():

    result = None
    error = None

    if request.method == "POST":
        try:
            result = url_opener.open_url(request.form.get("url"))
            notify("Remote", f"Opened {result}")
        except url_opener.InvalidURLError as exc:
            error = str(exc)

    return render_template("open_url.html", result=result, error=error)


@tools.route("/api/open-url", methods=["POST"])
@require_personal_device
def api_open_url():
    """
    JSON endpoint meant for phone automation (iOS Shortcuts, Tasker,
    a share-sheet action, etc): POST {"url": "https://..."}
    """

    data = request.get_json(silent=True) or {}

    try:
        opened = url_opener.open_url(data.get("url"))
        notify("Remote", f"Opened {opened}")
        return jsonify({"status": "ok", "url": opened})
    except url_opener.InvalidURLError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


# ---------------------------------------------------------------
# Clipboard sync
# ---------------------------------------------------------------

@tools.route("/clipboard", methods=["GET", "POST"])
@require_personal_device
def clipboard_view():

    message = None

    if request.method == "POST":
        clipboard.set_clipboard(request.form.get("text", ""))
        notify("Remote", "Clipboard updated")
        message = "Clipboard updated on laptop."

    current_text = clipboard.get_clipboard()

    return render_template(
        "clipboard.html",
        message=message,
        current_text=current_text,
    )


@tools.route("/api/clipboard", methods=["POST"])
@require_personal_device
def api_clipboard():

    data = request.get_json(silent=True) or {}
    clipboard.set_clipboard(data.get("text", ""))
    notify("Remote", "Clipboard updated")

    return jsonify({"status": "ok"})


# ---------------------------------------------------------------
# File transfer
# ---------------------------------------------------------------

@tools.route("/files", methods=["GET", "POST"])
@require_personal_device
def files_view():

    error = None

    if request.method == "POST":
        upload = request.files.get("file")

        if upload is None or not upload.filename:
            error = "No file selected."
        else:
            try:
                files.save_upload(upload)
            except ValueError as exc:
                error = str(exc)

    return render_template(
        "files.html",
        files=files.list_uploads(),
        error=error,
    )


@tools.route("/files/download/<path:filename>")
@require_personal_device
def download_file(filename):
    # send_from_directory guards against path traversal outside
    # the upload directory on its own.
    return send_from_directory(
        files.get_upload_dir(),
        filename,
        as_attachment=True,
    )
