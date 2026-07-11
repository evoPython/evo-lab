import shutil
import subprocess
import threading
import time

_lock = threading.Lock()
_latest_frame = None      # bytes, latest JPEG from phone camera
_camera_proc = None       # mpv window showing the mjpeg stream
_audio_proc = None        # ffplay reading a live audio pipe

WINDOW_TITLE = "Remote Camera"


class StreamError(Exception):
    pass


# --- camera (video) ---

def set_frame(raw_bytes):
    global _latest_frame
    if not raw_bytes:
        raise StreamError("Empty frame")
    with _lock:
        _latest_frame = raw_bytes


def mjpeg_generator():
    boundary = b"--frame"
    while True:
        with _lock:
            frame = _latest_frame
        if frame:
            yield (boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" +
                   frame + b"\r\n")
        time.sleep(0.15)


def camera_start(mjpeg_url):
    global _camera_proc
    if shutil.which("mpv") is None:
        raise StreamError("mpv not found (needed to display the camera window)")
    if _camera_proc and _camera_proc.poll() is None:
        return  # already running
    _camera_proc = subprocess.Popen(
        ["mpv", f"--title={WINDOW_TITLE}", "--no-audio", "--loop-file=inf", mjpeg_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def camera_stop():
    global _camera_proc, _latest_frame
    if _camera_proc and _camera_proc.poll() is None:
        _camera_proc.terminate()
    _camera_proc = None
    _latest_frame = None


def camera_is_running():
    return bool(_camera_proc and _camera_proc.poll() is None)


# --- microphone (audio only, no window) ---

def audio_start():
    global _audio_proc
    if shutil.which("ffplay") is None:
        raise StreamError("ffplay not found (needed to play live audio)")
    if _audio_proc and _audio_proc.poll() is None:
        return
    _audio_proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def audio_write(chunk):
    if not (_audio_proc and _audio_proc.poll() is None):
        raise StreamError("Audio stream not started")
    try:
        _audio_proc.stdin.write(chunk)
        _audio_proc.stdin.flush()
    except Exception as exc:
        raise StreamError(f"Failed writing audio chunk: {exc}")


def audio_stop():
    global _audio_proc
    if _audio_proc and _audio_proc.poll() is None:
        try:
            _audio_proc.stdin.close()
        except Exception:
            pass
        _audio_proc.terminate()
    _audio_proc = None
