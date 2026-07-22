import io
import os
import shutil
import zipfile
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename


class PathError(ValueError):
    """Raised when a client-supplied path is invalid or escapes the
    upload directory."""


def get_upload_dir():

    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)

    return upload_dir


def _normalize_rel(rel_path):
    """
    Turn a client-supplied relative path like "a/b/../c" into a clean,
    slash-separated path with every segment run through secure_filename.
    ".." segments and empty segments are dropped rather than allowed to
    climb outside the upload root.
    """

    rel_path = (rel_path or "").strip().strip("/")

    if not rel_path or rel_path in (".", "./"):
        return ""

    parts = []
    for part in rel_path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise PathError("Invalid path")
        safe = secure_filename(part)
        if not safe:
            raise PathError("Invalid path")
        parts.append(safe)

    return "/".join(parts)


def resolve_path(rel_path, must_exist=True):
    """
    Resolve a client-supplied relative path to an absolute path inside
    the upload directory. Returns (abs_path, normalized_rel_path).
    """

    root = os.path.realpath(get_upload_dir())
    rel = _normalize_rel(rel_path)
    candidate = os.path.realpath(os.path.join(root, rel))

    if candidate != root and not candidate.startswith(root + os.sep):
        raise PathError("Invalid path")

    if must_exist and not os.path.exists(candidate):
        raise FileNotFoundError(rel or ".")

    return candidate, rel


def _dedupe_path(path):
    """If `path` already exists, append " (1)", " (2)", etc. before the
    extension until a free name is found."""

    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def list_dir(rel_path=""):
    """List the contents of a directory inside the upload root.
    Folders are sorted first, then files, both alphabetically."""

    abs_path, rel = resolve_path(rel_path, must_exist=True)

    if not os.path.isdir(abs_path):
        raise NotADirectoryError(rel or ".")

    entries = []
    for name in os.listdir(abs_path):
        full = os.path.join(abs_path, name)
        try:
            stat = os.stat(full)
        except OSError:
            continue

        is_dir = os.path.isdir(full)
        entries.append({
            "name": name,
            "path": f"{rel}/{name}".strip("/"),
            "is_dir": is_dir,
            "size": None if is_dir else stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    return entries


def save_upload(file_storage, rel_dir=""):
    """
    Saves an uploaded file into a folder inside the upload directory.
    Filenames are sanitized with secure_filename so path traversal
    (e.g. "../../etc/passwd") and unsafe characters can't reach the
    filesystem. If a file of the same name already exists, the new
    file is saved alongside it as "name (1).ext".
    """

    filename = secure_filename(file_storage.filename or "")

    if not filename:
        raise ValueError("Invalid or missing filename")

    dir_abs, _ = resolve_path(rel_dir, must_exist=True)

    if not os.path.isdir(dir_abs):
        raise ValueError("Target is not a folder")

    destination = _dedupe_path(os.path.join(dir_abs, filename))
    file_storage.save(destination)

    return os.path.basename(destination)


def make_dir(rel_dir, name):
    """Create a new folder named `name` inside `rel_dir`."""

    dir_abs, _ = resolve_path(rel_dir, must_exist=True)

    if not os.path.isdir(dir_abs):
        raise ValueError("Target is not a folder")

    safe_name = secure_filename(name or "")
    if not safe_name:
        raise ValueError("Invalid folder name")

    target = os.path.join(dir_abs, safe_name)
    if os.path.exists(target):
        raise ValueError("A file or folder with that name already exists")

    os.makedirs(target)

    return safe_name


def rename_entry(rel_path, new_name):
    """Rename a file or folder, keeping it in the same parent folder."""

    abs_path, rel = resolve_path(rel_path, must_exist=True)

    if not rel:
        raise ValueError("Cannot rename the root folder")

    safe_name = secure_filename(new_name or "")
    if not safe_name:
        raise ValueError("Invalid name")

    new_abs = os.path.join(os.path.dirname(abs_path), safe_name)
    if os.path.exists(new_abs):
        raise ValueError("A file or folder with that name already exists")

    os.rename(abs_path, new_abs)

    return safe_name


def move_entry(rel_path, dest_dir):
    """Move a file or folder into `dest_dir` (another folder inside the
    upload root). Refuses to move a folder into itself or one of its
    own descendants, and dedupes the destination name if needed."""

    abs_path, rel = resolve_path(rel_path, must_exist=True)

    if not rel:
        raise ValueError("Cannot move the root folder")

    dest_abs, dest_rel = resolve_path(dest_dir, must_exist=True)

    if not os.path.isdir(dest_abs):
        raise ValueError("Destination is not a folder")

    src_parent = os.path.dirname(abs_path)
    if os.path.realpath(dest_abs) == os.path.realpath(src_parent):
        # Already there — no-op.
        return os.path.basename(abs_path), dest_rel

    if os.path.isdir(abs_path):
        real_src = os.path.realpath(abs_path)
        real_dest = os.path.realpath(dest_abs)
        if real_dest == real_src or real_dest.startswith(real_src + os.sep):
            raise ValueError("Can't move a folder into itself")

    target = _dedupe_path(os.path.join(dest_abs, os.path.basename(abs_path)))
    shutil.move(abs_path, target)

    return os.path.basename(target), dest_rel


def delete_entry(rel_path):
    """Delete a file, or a folder and everything inside it."""

    abs_path, rel = resolve_path(rel_path, must_exist=True)

    if not rel:
        raise ValueError("Cannot delete the root folder")

    if os.path.isdir(abs_path):
        shutil.rmtree(abs_path)
    else:
        os.remove(abs_path)


def build_zip(rel_paths):
    """Bundle one or more files/folders (given as relative paths) into
    an in-memory zip archive and return a BytesIO ready to be sent."""

    root = os.path.realpath(get_upload_dir())
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in rel_paths:
            abs_path, rel = resolve_path(rel_path, must_exist=True)

            if os.path.isdir(abs_path):
                for dirpath, _, filenames in os.walk(abs_path):
                    for fn in filenames:
                        fp = os.path.join(dirpath, fn)
                        zf.write(fp, os.path.relpath(fp, root))
            else:
                zf.write(abs_path, os.path.relpath(abs_path, root))

    buf.seek(0)
    return buf
