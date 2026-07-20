import shutil
import subprocess

# unit separator — won't collide with real track/artist/album text,
# unlike '|' which does show up in titles sometimes.
_SEP = "\x1f"
_STATUS_FORMAT = _SEP.join([
    "{{status}}",
    "{{title}}",
    "{{artist}}",
    "{{album}}",
    "{{mpris:length}}",
    "{{position}}",
])

# Some players report mpris:length as an unsigned -1 (~18.4 * 10^18 us)
# for live/streaming sources with no known duration. Anything longer
# than a day is obviously bogus, so treat it as "unknown" instead.
_MAX_SANE_LENGTH_US = 24 * 3600 * 1_000_000


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
    return result.stdout


def play_pause():
    _playerctl("play-pause")


def pause():
    _playerctl("pause")


def next_track():
    _playerctl("next")


def prev_track():
    _playerctl("previous")


def _empty_status():
    return {
        "playing": False,
        "status": "Stopped",
        "title": None,
        "artist": None,
        "album": None,
        "length_seconds": None,
        "position_seconds": None,
    }


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_status():
    """
    Current playback status straight from playerctl: whether
    something's playing/paused, the track's title/artist/album, and
    how far into it we are. Uses a single `playerctl metadata
    --format` call rather than separate `playerctl status` /
    `playerctl position` calls, since the format string can pull
    everything from the active player in one subprocess.
    """

    if shutil.which("playerctl") is None:
        raise MediaKeyError("playerctl not found")

    try:
        result = subprocess.run(
            ["playerctl", "metadata", "--format", _STATUS_FORMAT],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        raise MediaKeyError(str(exc))

    # Non-zero exit / empty output means no player is running or
    # nothing is loaded right now — a normal state, not an error.
    if result.returncode != 0 or not result.stdout.strip():
        return _empty_status()

    parts = result.stdout.rstrip("\n").split(_SEP)
    parts += [""] * (6 - len(parts))
    status, title, artist, album, length_raw, position_raw = parts[:6]

    length_us = _to_int(length_raw)
    if length_us is not None and (length_us <= 0 or length_us > _MAX_SANE_LENGTH_US):
        length_us = None

    position_us = _to_int(position_raw)
    if position_us is not None and position_us < 0:
        position_us = None

    title = title.strip()
    if not title:
        # Player is present (e.g. an idle Spotify instance) but has
        # nothing loaded — same as no player at all, as far as the UI
        # is concerned.
        return _empty_status()

    return {
        "playing": status.strip().lower() == "playing",
        "status": status.strip() or "Unknown",
        "title": title,
        "artist": artist.strip() or None,
        "album": album.strip() or None,
        "length_seconds": round(length_us / 1_000_000, 1) if length_us is not None else None,
        "position_seconds": round(position_us / 1_000_000, 1) if position_us is not None else None,
    }
