import json
import os
import threading
import time

from flask import current_app

_lock = threading.Lock()
_INDEX_NAME = "library.json"


def get_music_dir():
    music_dir = current_app.config["MUSIC_DIR"]
    os.makedirs(music_dir, exist_ok=True)
    return music_dir


def _index_path():
    return os.path.join(get_music_dir(), _INDEX_NAME)


def _load_index():
    path = _index_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_index(index):
    with open(_index_path(), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def _read_tags_fallback(path):
    """Best-effort duration lookup for mp3 files that aren't in the
    index (e.g. dropped in manually), using mutagen if available."""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return round(audio.info.length)
    except Exception:
        return None


def add_entry(filename, meta):
    """Record/replace metadata for a downloaded track."""
    with _lock:
        index = _load_index()
        meta = dict(meta)
        meta.setdefault("added_at", time.time())
        index[filename] = meta
        _save_index(index)


def remove_entry(filename):
    with _lock:
        index = _load_index()
        index.pop(filename, None)
        _save_index(index)


def update_entry(filename, updates):
    """
    Merge `updates` (title/uploader) into a track's stored metadata.
    Only touches library.json — the file on disk and its filename
    are untouched, so playback/playlist references stay valid.
    """
    safe_name = os.path.basename(filename)
    full_path = os.path.join(get_music_dir(), safe_name)
    if not os.path.isfile(full_path):
        raise FileNotFoundError(safe_name)
    with _lock:
        index = _load_index()
        meta = index.get(safe_name, {})
        meta = {**meta, **updates}
        index[safe_name] = meta
        _save_index(index)
    return {
        "filename": safe_name,
        "title": meta.get("title") or os.path.splitext(safe_name)[0],
        "uploader": meta.get("uploader") or None,
    }


def list_tracks():
    """
    Every .mp3 in the music dir, enriched with whatever metadata we
    have for it (title/artist/thumbnail/source from a download, or a
    best-effort fallback for files that just showed up on disk).
    """
    music_dir = get_music_dir()
    index = _load_index()

    tracks = []
    for name in sorted(os.listdir(music_dir)):
        if not name.lower().endswith(".mp3"):
            continue
        full_path = os.path.join(music_dir, name)
        if not os.path.isfile(full_path):
            continue

        meta = index.get(name, {})
        duration = meta.get("duration")
        if duration is None:
            duration = _read_tags_fallback(full_path)
        added_at = meta.get("added_at")
        if added_at is None:
            added_at = os.path.getmtime(full_path)

        tracks.append({
            "filename": name,
            "title": meta.get("title") or os.path.splitext(name)[0],
            "uploader": meta.get("uploader"),
            "thumbnail": meta.get("thumbnail"),
            "source_url": meta.get("source_url"),
            "duration": duration,
            "size_bytes": os.path.getsize(full_path),
            "added_at": added_at,
        })

    return tracks


def delete_track(filename):
    music_dir = get_music_dir()
    safe_name = os.path.basename(filename)
    full_path = os.path.join(music_dir, safe_name)
    if not os.path.isfile(full_path):
        raise FileNotFoundError(safe_name)
    os.remove(full_path)
    remove_entry(safe_name)
