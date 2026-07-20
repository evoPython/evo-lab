import json
import os
import threading
import time
import uuid

from app.media import music_library

_lock = threading.Lock()
_FILE_NAME = "playlists.json"


class PlaylistError(Exception):
    pass


def _path():
    return os.path.join(music_library.get_music_dir(), _FILE_NAME)


def _load():
    path = _path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data):
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_playlists():
    data = _load()
    return sorted(
        (
            {"id": pid, "name": p["name"], "count": len(p.get("filenames", []))}
            for pid, p in data.items()
        ),
        key=lambda p: p["name"].lower(),
    )


def get_playlist(playlist_id):
    """Playlist detail, tracks resolved against the library (missing
    files — deleted since being added — are silently dropped)."""
    data = _load()
    p = data.get(playlist_id)
    if not p:
        raise PlaylistError("Playlist not found")

    by_name = {t["filename"]: t for t in music_library.list_tracks()}
    tracks = [by_name[fn] for fn in p.get("filenames", []) if fn in by_name]
    return {"id": playlist_id, "name": p["name"], "tracks": tracks}


def create_playlist(name):
    name = (name or "").strip()
    if not name:
        raise PlaylistError("Playlist name is required")
    with _lock:
        data = _load()
        pid = uuid.uuid4().hex[:12]
        data[pid] = {"name": name, "filenames": [], "created": time.time()}
        _save(data)
        return pid


def rename_playlist(playlist_id, name):
    name = (name or "").strip()
    if not name:
        raise PlaylistError("Playlist name is required")
    with _lock:
        data = _load()
        if playlist_id not in data:
            raise PlaylistError("Playlist not found")
        data[playlist_id]["name"] = name
        _save(data)


def delete_playlist(playlist_id):
    with _lock:
        data = _load()
        if data.pop(playlist_id, None) is None:
            raise PlaylistError("Playlist not found")
        _save(data)


def add_track(playlist_id, filename):
    with _lock:
        data = _load()
        p = data.get(playlist_id)
        if not p:
            raise PlaylistError("Playlist not found")
        if filename not in p.setdefault("filenames", []):
            p["filenames"].append(filename)
            _save(data)


def remove_track(playlist_id, filename):
    with _lock:
        data = _load()
        p = data.get(playlist_id)
        if not p:
            raise PlaylistError("Playlist not found")
        if filename in p.get("filenames", []):
            p["filenames"].remove(filename)
            _save(data)
