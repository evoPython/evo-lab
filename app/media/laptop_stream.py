import shutil
import subprocess
import threading

_lock = threading.Lock()
_camera_proc = None
_mic_proc = None


class LaptopStreamError(Exception):
    pass


def _start_ffmpeg(*args):
    if shutil.which("ffmpeg") is None:
        raise LaptopStreamError("ffmpeg not found")
    return subprocess.Popen(
        ["ffmpeg", *args, "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def _kill(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


# --- camera ---

def camera_generator():
    global _camera_proc
    with _lock:
        _kill(_camera_proc)
        _camera_proc = _start_ffmpeg(
            "-f", "v4l2", "-i", "/dev/video0",
            "-f", "mpjpeg", "-q:v", "5", "-r", "10",
        )
        proc = _camera_proc
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        with _lock:
            _kill(proc)
            if proc is _camera_proc:
                _camera_proc = None


def camera_stop():
    global _camera_proc
    with _lock:
        _kill(_camera_proc)
        _camera_proc = None


# --- microphone ---

def mic_generator():
    global _mic_proc
    with _lock:
        _kill(_mic_proc)
        _mic_proc = _start_ffmpeg(
            "-f", "pulse", "-i", "default",
            "-f", "mp3", "-b:a", "96k",
        )
        proc = _mic_proc
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        with _lock:
            _kill(proc)
            if proc is _mic_proc:
                _mic_proc = None


def mic_stop():
    global _mic_proc
    with _lock:
        _kill(_mic_proc)
        _mic_proc = None
