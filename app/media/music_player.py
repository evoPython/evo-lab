import itertools
import json
import os
import shutil
import socket
import subprocess
import threading
import time

from flask import current_app

_lock = threading.Lock()
_proc = None
_current = {"filename": None, "title": None}
_req_id = itertools.count(1)

SOCK_PATH = "/tmp/evo-music-mpv.sock"


class PlayerError(Exception):
    pass


def _ensure_running():
    global _proc
    if _proc and _proc.poll() is None:
        return
    if shutil.which("mpv") is None:
        raise PlayerError("mpv not found (needed to play music on the laptop)")
    with _lock:
        if _proc and _proc.poll() is None:
            return
        if os.path.exists(SOCK_PATH):
            try:
                os.remove(SOCK_PATH)
            except OSError:
                pass
        _proc = subprocess.Popen(
            [
                "mpv", "--idle=yes", "--no-video", "--no-terminal",
                f"--input-ipc-server={SOCK_PATH}",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            if os.path.exists(SOCK_PATH):
                return
            time.sleep(0.1)
        raise PlayerError("mpv did not create its IPC socket in time")


def _command(cmd):
    """Send one JSON-IPC command to mpv and return its 'data' field."""
    _ensure_running()
    rid = next(_req_id)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect(SOCK_PATH)
        sock.sendall((json.dumps({"command": cmd, "request_id": rid}) + "\n").encode())

        buf = b""
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            for line in buf.split(b"\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("request_id") == rid:
                    err = data.get("error")
                    if err not in (None, "success"):
                        raise PlayerError(err)
                    return data.get("data")
        raise PlayerError("mpv IPC timed out")
    except OSError as exc:
        raise PlayerError(f"mpv IPC error: {exc}")
    finally:
        sock.close()


def _abs_path_for(filename):
    music_dir = current_app.config["MUSIC_DIR"]
    return os.path.join(music_dir, os.path.basename(filename))


def play(filename, title=None):
    path = _abs_path_for(filename)
    if not os.path.isfile(path):
        raise PlayerError(f"{filename} not found in library")
    _command(["loadfile", path, "replace"])
    _command(["set_property", "pause", False])
    with _lock:
        _current["filename"] = filename
        _current["title"] = title or filename


def pause():
    _command(["set_property", "pause", True])


def resume():
    _command(["set_property", "pause", False])


def toggle():
    _command(["cycle", "pause"])


def stop():
    _command(["stop"])
    with _lock:
        _current["filename"] = None
        _current["title"] = None


def seek(position_seconds):
    try:
        pos = max(0.0, float(position_seconds))
    except (TypeError, ValueError):
        raise PlayerError("Invalid seek position")
    _command(["set_property", "time-pos", pos])


def set_volume(value):
    try:
        vol = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        raise PlayerError("Invalid volume")
    _command(["set_property", "volume", vol])


def _get_property(name, default=None):
    try:
        return _command(["get_property", name])
    except PlayerError:
        return default


def status():
    if not (_proc and _proc.poll() is None):
        return {
            "running": False, "playing": False,
            "filename": None, "title": None,
            "position": None, "duration": None, "volume": None,
        }

    with _lock:
        filename = _current["filename"]
        title = _current["title"]

    idle = _get_property("idle-active", False)
    if idle or not filename:
        return {
            "running": True, "playing": False,
            "filename": None, "title": None,
            "position": None, "duration": None,
            "volume": _get_property("volume"),
        }

    paused = _get_property("pause", True)
    return {
        "running": True,
        "playing": not paused,
        "filename": filename,
        "title": title,
        "position": _get_property("time-pos"),
        "duration": _get_property("duration"),
        "volume": _get_property("volume"),
    }
