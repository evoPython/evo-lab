from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    send_from_directory,
    send_file,
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

@tools.route("/files")
@require_personal_device
def files_view():
    return render_template("files.html")


def _path_error_response(exc):
    if isinstance(exc, FileNotFoundError):
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "error", "message": str(exc) or "Invalid request"}), 400


@tools.route("/files/api/list")
@require_personal_device
def api_list_files():
    path = request.args.get("path", "")
    try:
        entries = files.list_dir(path)
    except (files.PathError, FileNotFoundError, NotADirectoryError) as exc:
        return _path_error_response(exc)

    resp = jsonify({"status": "ok", "path": path, "entries": entries})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@tools.route("/files/api/upload", methods=["POST"])
@require_personal_device
def api_upload_file():
    path = request.form.get("path", "")
    upload = request.files.get("file")

    if upload is None or not upload.filename:
        return jsonify({"status": "error", "message": "No file selected."}), 400

    try:
        saved = files.save_upload(upload, path)
    except (ValueError, files.PathError, FileNotFoundError) as exc:
        return _path_error_response(exc)

    notify("Remote", f"Uploaded {saved}")
    return jsonify({"status": "ok", "name": saved})


@tools.route("/files/api/mkdir", methods=["POST"])
@require_personal_device
def api_mkdir():
    data = request.get_json(silent=True) or {}

    try:
        name = files.make_dir(data.get("path", ""), data.get("name", ""))
    except (ValueError, files.PathError, FileNotFoundError) as exc:
        return _path_error_response(exc)

    return jsonify({"status": "ok", "name": name})


@tools.route("/files/api/rename", methods=["POST"])
@require_personal_device
def api_rename():
    data = request.get_json(silent=True) or {}

    try:
        name = files.rename_entry(data.get("path", ""), data.get("new_name", ""))
    except (ValueError, files.PathError, FileNotFoundError) as exc:
        return _path_error_response(exc)

    return jsonify({"status": "ok", "name": name})


@tools.route("/files/api/move", methods=["POST"])
@require_personal_device
def api_move():
    data = request.get_json(silent=True) or {}
    paths = data.get("paths") or []
    dest = data.get("dest", "")

    errors = []
    moved = 0
    for p in paths:
        try:
            files.move_entry(p, dest)
            moved += 1
        except (ValueError, files.PathError, FileNotFoundError) as exc:
            errors.append({"path": p, "message": str(exc)})

    if moved:
        notify("Remote", f"Moved {moved} item(s)")

    if errors and not moved:
        return jsonify({"status": "error", "errors": errors, "message": errors[0]["message"]}), 400
    if errors:
        return jsonify({"status": "partial", "errors": errors}), 207

    return jsonify({"status": "ok"})


@tools.route("/files/api/delete", methods=["POST"])
@require_personal_device
def api_delete():
    data = request.get_json(silent=True) or {}
    paths = data.get("paths") or []

    errors = []
    deleted = 0
    for p in paths:
        try:
            files.delete_entry(p)
            deleted += 1
        except (ValueError, files.PathError, FileNotFoundError) as exc:
            errors.append({"path": p, "message": str(exc)})

    if deleted:
        notify("Remote", f"Deleted {deleted} item(s)")

    if errors:
        return jsonify({"status": "partial", "errors": errors}), 207

    return jsonify({"status": "ok"})


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


@tools.route("/files/view/<path:filename>")
@require_personal_device
def view_file(filename):
    # Same as download_file but without forcing a "Save As" — used as
    # the src for image/video/audio/pdf previews so a click just shows
    # the file instead of triggering a browser download.
    return send_from_directory(
        files.get_upload_dir(),
        filename,
        as_attachment=False,
    )


@tools.route("/files/api/download-zip", methods=["POST"])
@require_personal_device
def api_download_zip():
    data = request.get_json(silent=True) or {}
    paths = data.get("paths") or []

    if not paths:
        return jsonify({"status": "error", "message": "Nothing selected"}), 400

    try:
        buf = files.build_zip(paths)
    except (files.PathError, FileNotFoundError) as exc:
        return _path_error_response(exc)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="files.zip",
    )
