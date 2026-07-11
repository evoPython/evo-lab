import shutil
import subprocess


class MediaKeyError(Exception):
    pass


def _playerctl(*args):
    if shutil.which("playerctl") is None:
        raise MediaKeyError("playerctl not found")
    try:
        result = subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=5)
    except Exception as exc:
        raise MediaKeyError(str(exc))
    if result.returncode != 0:
        raise MediaKeyError(result.stderr.strip() or "playerctl failed")


def play_pause():
    _playerctl("play-pause")


def next_track():
    _playerctl("next")


def prev_track():
    _playerctl("previous")
