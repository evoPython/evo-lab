import os

from flask import current_app
from werkzeug.utils import secure_filename


def get_upload_dir():

    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)

    return upload_dir


def save_upload(file_storage):
    """
    Saves an uploaded file into the configured upload directory.
    Filenames are sanitized with secure_filename so path traversal
    (e.g. "../../etc/passwd") and unsafe characters can't reach the
    filesystem.
    """

    filename = secure_filename(file_storage.filename or "")

    if not filename:
        raise ValueError("Invalid or missing filename")

    upload_dir = get_upload_dir()
    destination = os.path.join(upload_dir, filename)

    file_storage.save(destination)

    return filename


def list_uploads():

    upload_dir = get_upload_dir()

    entries = [
        name for name in os.listdir(upload_dir)
        if os.path.isfile(os.path.join(upload_dir, name))
    ]

    return sorted(entries)
