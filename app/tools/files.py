import io
import os
import re
import shutil
import threading
import time
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


_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Large single POST requests are what fail on some LAN paths (routers/
# APs that choke on sustained big transfers, even though the same file
# sails through over a tunnel like Tailscale). Splitting big uploads
# into small chunks client-side and reassembling them here keeps every
# individual request small regardless of the underlying cause. This
# staging area lives *outside* UPLOAD_DIR (a sibling folder) so
# in-progress chunk sets never show up in the file browser.
_CHUNK_MAX_AGE_SECONDS = 6 * 60 * 60  # clean up abandoned sessions after 6h

# The client now sends chunks for one file concurrently (for speed), so
# more than one chunk of the same upload can finish "at the same time"
# and each check whether the set is now complete. Only one of them
# should actually assemble + clean up the session; this guards that.
_chunk_locks_guard = threading.Lock()
_chunk_locks = {}


def _get_session_lock(upload_id):
    with _chunk_locks_guard:
        lock = _chunk_locks.get(upload_id)
        if lock is None:
            lock = threading.Lock()
            _chunk_locks[upload_id] = lock
        return lock


def _drop_session_lock(upload_id):
    with _chunk_locks_guard:
        _chunk_locks.pop(upload_id, None)


def get_chunk_tmp_dir():
    tmp_dir = os.path.join(os.path.dirname(get_upload_dir().rstrip(os.sep)), ".upload_chunks")
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir


def _cleanup_stale_chunk_sessions(tmp_dir, keep):
    """Best-effort cleanup of abandoned chunk sessions (e.g. the user
    closed the tab mid-upload). Never touches `keep`, the session
    currently being written to."""

    try:
        now = time.time()
        for name in os.listdir(tmp_dir):
            if name == keep:
                continue
            session_dir = os.path.join(tmp_dir, name)
            try:
                if now - os.path.getmtime(session_dir) > _CHUNK_MAX_AGE_SECONDS:
                    shutil.rmtree(session_dir, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


def save_chunk(upload_id, chunk_index, total_chunks, filename, rel_dir, chunk_storage):
    """
    Save one chunk of a larger upload. Chunks for the same upload_id
    may arrive concurrently from the client. Once every chunk has
    arrived, assembles them into the final file (in order) and returns
    its saved name — but only one concurrent caller will ever actually
    do that assembly (guarded by a per-upload lock); the rest return
    None, same as if their chunk simply wasn't the last one to land.
    """

    if not upload_id or not _UPLOAD_ID_RE.match(upload_id):
        raise ValueError("Invalid upload id")

    try:
        chunk_index = int(chunk_index)
        total_chunks = int(total_chunks)
    except (TypeError, ValueError):
        raise ValueError("Invalid chunk index")

    if total_chunks <= 0 or not (0 <= chunk_index < total_chunks):
        raise ValueError("Invalid chunk index")

    safe_filename = secure_filename(filename or "")
    if not safe_filename:
        raise ValueError("Invalid or missing filename")

    dir_abs, _ = resolve_path(rel_dir, must_exist=True)
    if not os.path.isdir(dir_abs):
        raise ValueError("Target is not a folder")

    tmp_dir = get_chunk_tmp_dir()
    _cleanup_stale_chunk_sessions(tmp_dir, keep=upload_id)

    session_dir = os.path.join(tmp_dir, upload_id)
    os.makedirs(session_dir, exist_ok=True)

    # Write this chunk to disk first — outside the lock, so concurrent
    # chunks of the same upload can still be written in parallel. Only
    # the "is everything here yet, and if so let's assemble" step below
    # needs to be serialized.
    chunk_storage.save(os.path.join(session_dir, f"{chunk_index:06d}.part"))

    lock = _get_session_lock(upload_id)
    with lock:
        if not os.path.isdir(session_dir):
            # Another concurrent chunk request already finished
            # assembling and cleaned up the session.
            return None

        received = {
            name for name in os.listdir(session_dir) if name.endswith(".part")
        }
        if len(received) < total_chunks:
            return None

        destination = _dedupe_path(os.path.join(dir_abs, safe_filename))
        with open(destination, "wb") as out:
            for i in range(total_chunks):
                part_path = os.path.join(session_dir, f"{i:06d}.part")
                with open(part_path, "rb") as part:
                    shutil.copyfileobj(part, out)

        shutil.rmtree(session_dir, ignore_errors=True)

    _drop_session_lock(upload_id)

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


def copy_entry(rel_path, dest_dir):
    """Copy a file or folder into `dest_dir` (another folder inside the
    upload root), leaving the original in place. Refuses to copy a
    folder into itself or one of its own descendants, and dedupes the
    destination name if needed."""

    abs_path, rel = resolve_path(rel_path, must_exist=True)

    if not rel:
        raise ValueError("Cannot copy the root folder")

    dest_abs, dest_rel = resolve_path(dest_dir, must_exist=True)

    if not os.path.isdir(dest_abs):
        raise ValueError("Destination is not a folder")

    if os.path.isdir(abs_path):
        real_src = os.path.realpath(abs_path)
        real_dest = os.path.realpath(dest_abs)
        if real_dest == real_src or real_dest.startswith(real_src + os.sep):
            raise ValueError("Can't copy a folder into itself")

    target = _dedupe_path(os.path.join(dest_abs, os.path.basename(abs_path)))

    if os.path.isdir(abs_path):
        shutil.copytree(abs_path, target)
    else:
        shutil.copy2(abs_path, target)

    return os.path.basename(target), dest_rel


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
