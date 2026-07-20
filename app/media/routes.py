import shutil
import threading
import time
import uuid

from flask import (
    Blueprint, current_app, jsonify, request, Response, render_template,
    send_from_directory,
)

from app.core.security import require_personal_device
from app.core.notify import notify
from app.media import stream, laptop_stream, music_library, music_search, music_player, playlists
from app.niri import client as niri_client
from app.controls import media_keys


media = Blueprint("media", __name__, url_prefix="/media")

# Tracks whether "typical laptop media" (Spotify, a browser tab, etc.,
# as seen via playerctl) was already playing the last time /now_playing
# was polled. Lets us tell "it's been playing all along" apart from
# "it just started" — only the latter should steal focus away from a
# track already going in our own mpv instance. None means "no poll yet",
# so a fresh server start never yanks control away from something that
# (for all we know) had been playing before we ever looked.
_ext_was_playing = None

# In-memory tracking for background download jobs, polled by the
# frontend for live MB/speed progress. Small personal-scale tool, so
# a plain dict + lock is enough — no need for a real job queue.
_download_jobs = {}
_download_jobs_lock = threading.Lock()
_JOB_TTL = 300  # seconds a finished/errored job stays around for a late poll


def _prune_download_jobs():
    cutoff = time.time() - _JOB_TTL
    for jid in [j for j, v in _download_jobs.items() if v.get("done_at", time.time()) < cutoff]:
        _download_jobs.pop(jid, None)


@media.route("/stream/mjpeg")
def stream_mjpeg():
    # Fetched by mpv running locally on the laptop, not by the phone,
    # so it isn't gated behind require_personal_device (mpv doesn't
    # send the pairing cookie). It only ever serves whatever frame
    # the paired device most recently pushed.
    return Response(
        stream.mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@media.route("/stream/frame", methods=["POST"])
@require_personal_device
def stream_frame():
    try:
        stream.set_frame(request.get_data())
        return jsonify({"status": "ok"})
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/stream/camera/start", methods=["POST"])
@require_personal_device
def camera_start():
    mjpeg_url = request.host_url.rstrip("/") + "/media/stream/mjpeg"
    try:
        stream.camera_start(mjpeg_url)
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    # Give the mpv window a moment to appear, then focus it.
    focused = False
    for _ in range(10):
        time.sleep(0.3)
        try:
            windows = niri_client.get_windows()
        except niri_client.NiriError:
            continue
        match = next((w for w in windows if stream.WINDOW_TITLE in (w.get("title") or "")), None)
        if match:
            try:
                niri_client.run_action("focus-window", window_id=match["id"])
                focused = True
            except niri_client.NiriError:
                pass
            break

    notify("Remote", "Camera stream started")
    return jsonify({"status": "ok", "focused": focused})


@media.route("/stream/camera/stop", methods=["POST"])
@require_personal_device
def camera_stop():
    stream.camera_stop()
    notify("Remote", "Camera stream stopped")
    return jsonify({"status": "ok"})


@media.route("/stream/audio/start", methods=["POST"])
@require_personal_device
def audio_start():
    try:
        stream.audio_start()
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    notify("Remote", "Mic stream started")
    return jsonify({"status": "ok"})


@media.route("/stream/audio/chunk", methods=["POST"])
@require_personal_device
def audio_chunk():
    try:
        stream.audio_write(request.get_data())
        return jsonify({"status": "ok"})
    except stream.StreamError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/stream/audio/stop", methods=["POST"])
@require_personal_device
def audio_stop():
    stream.audio_stop()
    notify("Remote", "Mic stream stopped")
    return jsonify({"status": "ok"})


# --- Laptop -> phone: view/hear the laptop's own camera and mic ---

@media.route("/laptop/camera/stream")
@require_personal_device
def laptop_camera_stream():
    if not shutil.which("ffmpeg"):
        return jsonify({"error": "ffmpeg not found"}), 500
    return Response(
        laptop_stream.camera_generator(),
        mimetype="multipart/x-mixed-replace; boundary=ffmpeg",
    )


@media.route("/laptop/camera/stop", methods=["POST"])
@require_personal_device
def laptop_camera_stop():
    laptop_stream.camera_stop()
    notify("Remote", "Laptop camera stopped")
    return jsonify({"status": "ok"})


@media.route("/laptop/mic/stream")
@require_personal_device
def laptop_mic_stream():
    if not shutil.which("ffmpeg"):
        return jsonify({"error": "ffmpeg not found"}), 500
    return Response(laptop_stream.mic_generator(), mimetype="audio/mpeg")


@media.route("/laptop/mic/stop", methods=["POST"])
@require_personal_device
def laptop_mic_stop():
    laptop_stream.mic_stop()
    notify("Remote", "Laptop mic stopped")
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------
# Music: search + download (yt-dlp) and playback (laptop via mpv
# IPC, phone via plain HTTP audio streaming, or both at once).
# ---------------------------------------------------------------

@media.route("/music")
@require_personal_device
def music_page():
    return render_template("music.html")


@media.route("/music/artists")
@require_personal_device
def music_artists_page():
    return render_template("artists.html")


@media.route("/music/api/library")
@require_personal_device
def music_library_list():
    return jsonify({"tracks": music_library.list_tracks()})


@media.route("/music/api/search")
@require_personal_device
def music_search_route():
    query = request.args.get("q", "")
    try:
        results = music_search.search(query)
        return jsonify({"results": results})
    except music_search.MusicSearchError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@media.route("/music/api/download", methods=["POST"])
@require_personal_device
def music_download():
    data = request.get_json(silent=True) or {}
    video = data.get("id") or data.get("url")
    if not video:
        return jsonify({"status": "error", "message": "Missing id or url"}), 400

    app = current_app._get_current_object()

    with _download_jobs_lock:
        _prune_download_jobs()
        job_id = uuid.uuid4().hex
        _download_jobs[job_id] = {
            "status": "downloading",
            "downloaded_bytes": 0,
            "total_bytes": None,
            "speed": None,
            "started_at": time.time(),
            "updated_at": time.time(),
        }

    def on_progress(d):
        with _download_jobs_lock:
            job = _download_jobs.get(job_id)
            if not job:
                return
            if d.get("status") == "downloading":
                job["status"] = "downloading"
                job["downloaded_bytes"] = d.get("downloaded_bytes") or 0
                job["total_bytes"] = d.get("total_bytes") or d.get("total_bytes_estimate")
                job["speed"] = d.get("speed")
                job["updated_at"] = time.time()
            elif d.get("status") == "finished":
                # raw download done, ffmpeg is now extracting/transcoding
                job["status"] = "processing"
                job["updated_at"] = time.time()

    def run():
        try:
            with app.app_context():
                result = music_search.download_mp3(video, music_library.get_music_dir(), progress_cb=on_progress)
                music_library.add_entry(result["filename"], result["meta"])
                notify("Remote", f"Downloaded {result['meta'].get('title') or result['filename']}")
            with _download_jobs_lock:
                _download_jobs[job_id] = {
                    "status": "done",
                    "done_at": time.time(),
                    "track": {**result["meta"], "filename": result["filename"]},
                }
        except music_search.MusicSearchError as exc:
            with _download_jobs_lock:
                _download_jobs[job_id] = {"status": "error", "done_at": time.time(), "message": str(exc)}
        except Exception as exc:
            # Any other unexpected failure (e.g. a bug in add_entry/notify)
            # should still surface to the UI instead of leaving the job
            # stuck on "Starting..." forever with no visible error.
            with _download_jobs_lock:
                _download_jobs[job_id] = {"status": "error", "done_at": time.time(), "message": str(exc)}

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "ok", "job_id": job_id})


@media.route("/music/api/download/progress/<job_id>")
@require_personal_device
def music_download_progress(job_id):
    with _download_jobs_lock:
        job = _download_jobs.get(job_id)
        if not job:
            return jsonify({"status": "error", "message": "Unknown or expired download"}), 404
        if (
            job.get("status") == "downloading"
            and not job.get("downloaded_bytes")
            and time.time() - job.get("updated_at", job.get("started_at", 0)) > 45
        ):
            job["status"] = "error"
            job["done_at"] = time.time()
            job["message"] = (
                "Stalled with no data received — likely blocked or throttled "
                "by YouTube. Try again in a bit."
            )
        return jsonify(dict(job))


@media.route("/music/api/library/<path:filename>", methods=["DELETE"])
@require_personal_device
def music_delete(filename):
    try:
        music_library.delete_track(filename)
        return jsonify({"status": "ok"})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Not found"}), 404


@media.route("/music/api/library/<path:filename>", methods=["PATCH"])
@require_personal_device
def music_update_track(filename):
    data = request.get_json(silent=True) or {}
    updates = {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"status": "error", "message": "Title can't be empty"}), 400
        updates["title"] = title
    if "uploader" in data:
        updates["uploader"] = (data.get("uploader") or "").strip() or None
    if not updates:
        return jsonify({"status": "error", "message": "Nothing to update"}), 400
    try:
        track = music_library.update_entry(filename, updates)
        return jsonify({"status": "ok", "track": track})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Not found"}), 404


@media.route("/music/stream/<path:filename>")
@require_personal_device
def music_stream(filename):
    # conditional=True (Flask's default) handles Range requests, so
    # phones can seek within the file via the native <audio> element.
    return send_from_directory(
        music_library.get_music_dir(),
        filename,
        mimetype="audio/mpeg",
        conditional=True,
    )


@media.route("/music/api/play", methods=["POST"])
@require_personal_device
def music_play():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    title = data.get("title")
    if not filename:
        return jsonify({"status": "error", "message": "Missing filename"}), 400
    _yield_external_to_local()
    try:
        music_player.play(filename, title=title)
        notify("Remote", f"Now playing: {title or filename}")
        return jsonify({"status": "ok"})
    except music_player.PlayerError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@media.route("/music/api/pause", methods=["POST"])
@require_personal_device
def music_pause():
    return _music_action(music_player.pause)


@media.route("/music/api/resume", methods=["POST"])
@require_personal_device
def music_resume():
    _yield_external_to_local()
    return _music_action(music_player.resume)


@media.route("/music/api/toggle", methods=["POST"])
@require_personal_device
def music_toggle():
    # Only worth yielding external media if this toggle is about to
    # start our track playing (paused -> playing). If it's going the
    # other way (playing -> paused) there's nothing new taking over
    # the speakers, so leave whatever else might be playing alone.
    if not music_player.status().get("playing"):
        _yield_external_to_local()
    return _music_action(music_player.toggle)


@media.route("/music/api/stop", methods=["POST"])
@require_personal_device
def music_stop():
    return _music_action(music_player.stop)


@media.route("/music/api/seek", methods=["POST"])
@require_personal_device
def music_seek():
    data = request.get_json(silent=True) or {}
    return _music_action(lambda: music_player.seek(data.get("position", 0)))


@media.route("/music/api/volume", methods=["POST"])
@require_personal_device
def music_volume():
    data = request.get_json(silent=True) or {}
    return _music_action(lambda: music_player.set_volume(data.get("value", 100)))


@media.route("/music/api/status")
@require_personal_device
def music_status():
    return jsonify(music_player.status())


@media.route("/music/api/now_playing")
@require_personal_device
def music_now_playing():
    """
    Unified "what's actually making sound on the laptop right now"
    view, so remote.html's playback widget and this music tool's own
    now-playing bar can share one source of truth instead of drifting
    apart.

    Prefers our own mpv instance (music_player.status()) since we
    control it directly over its IPC socket. If it has nothing loaded,
    falls back to whatever playerctl sees (Spotify, a YouTube tab,
    etc.) so "typical laptop media" still shows up here — just marked
    as downloadable, i.e. `downloadable: True`.

    Exception: if our own track is already playing and laptop-media
    freshly starts (wasn't playing on the previous poll, is now), that
    new media takes over — we stop our own track so it doesn't keep
    making sound underneath whatever the person actually just started,
    and report the laptop-media source instead.
    """
    global _ext_was_playing

    own = music_player.status()

    try:
        ext = media_keys.get_status()
    except media_keys.MediaKeyError:
        ext = None

    ext_playing_now = bool(ext and ext.get("title") and ext.get("playing"))

    # If we have a track loaded in our own mpv instance (playing OR
    # merely paused — either way nothing of ours is what's making
    # sound going forward) and laptop-media just transitioned from
    # not-playing to playing (someone hit play on Spotify/YouTube/
    # etc.), that new media should take over: stop our track and fall
    # through to reporting the laptop-media source below.
    # `_ext_was_playing is False` (not just falsy) is required so this
    # only fires on a genuine start, never on the first poll after a
    # server restart when we have no history to compare against.
    if own.get("filename") and ext_playing_now and _ext_was_playing is False:
        try:
            music_player.stop()
        except music_player.PlayerError:
            pass
        own = music_player.status()

    _ext_was_playing = ext_playing_now

    if own.get("filename"):
        return jsonify({
            "source": "music-tool",
            "playing": own["playing"],
            "title": own["title"],
            "artist": None,
            "album": None,
            "position": own["position"],
            "duration": own["duration"],
            "downloadable": False,
            "filename": own["filename"],
        })

    if ext and ext.get("title"):
        return jsonify({
            "source": "laptop-media",
            "playing": ext["playing"],
            "title": ext["title"],
            "artist": ext.get("artist"),
            "album": ext.get("album"),
            "position": ext.get("position_seconds"),
            "duration": ext.get("length_seconds"),
            "downloadable": True,
            "filename": None,
        })

    return jsonify({
        "source": "none", "playing": False,
        "title": None, "artist": None, "album": None,
        "position": None, "duration": None,
        "downloadable": False, "filename": None,
    })


@media.route("/music/api/download_current", methods=["POST"])
@require_personal_device
def music_download_current():
    """
    Takes whatever's currently playing via playerctl (typical laptop
    media — Spotify, a browser tab, etc.), builds a "<artist> <title>"
    search query out of it, and runs it through the exact same
    search-top-result -> yt-dlp download -> library-add pipeline as a
    manual search+download would. Only makes sense when nothing is
    already loaded in our own mpv instance (that case is already in
    the library and isn't "downloadable").
    """
    try:
        ext = media_keys.get_status()
    except media_keys.MediaKeyError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    if not ext.get("title"):
        return jsonify({"status": "error", "message": "Nothing playing on the laptop right now"}), 400

    query = ext["title"]
    if ext.get("artist"):
        query = f"{ext['artist']} {query}"

    try:
        results = music_search.search(query, limit=1)
    except music_search.MusicSearchError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    if not results or not results[0].get("id"):
        return jsonify({"status": "error", "message": f'No results found for "{query}"'}), 404

    try:
        result = music_search.download_mp3(results[0]["id"], music_library.get_music_dir())
    except music_search.MusicSearchError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    # The YouTube result's "uploader" is a channel name (often a label,
    # "Topic" channel, or unrelated uploader) — when the source player
    # (Spotify, etc.) told us the actual artist, that's more accurate
    # and worth keeping in the library entry over the YouTube one.
    if ext.get("artist"):
        result["meta"]["uploader"] = ext["artist"]

    music_library.add_entry(result["filename"], result["meta"])
    notify("Remote", f"Downloaded {result['meta'].get('title') or result['filename']}")

    return jsonify({
        "status": "ok",
        "query": query,
        "track": {**result["meta"], "filename": result["filename"]},
    })


@media.route("/playlists/api/list")
@require_personal_device
def playlists_list():
    return jsonify({"playlists": playlists.list_playlists()})


@media.route("/playlists/api/create", methods=["POST"])
@require_personal_device
def playlists_create():
    data = request.get_json(silent=True) or {}
    try:
        pid = playlists.create_playlist(data.get("name"))
        return jsonify({"status": "ok", "id": pid})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/playlists/api/<playlist_id>")
@require_personal_device
def playlists_get(playlist_id):
    try:
        return jsonify({"status": "ok", **playlists.get_playlist(playlist_id)})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404


@media.route("/playlists/api/<playlist_id>/rename", methods=["POST"])
@require_personal_device
def playlists_rename(playlist_id):
    data = request.get_json(silent=True) or {}
    try:
        playlists.rename_playlist(playlist_id, data.get("name"))
        return jsonify({"status": "ok"})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@media.route("/playlists/api/<playlist_id>", methods=["DELETE"])
@require_personal_device
def playlists_delete(playlist_id):
    try:
        playlists.delete_playlist(playlist_id)
        return jsonify({"status": "ok"})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404


@media.route("/playlists/api/<playlist_id>/tracks", methods=["POST"])
@require_personal_device
def playlists_add_track(playlist_id):
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"status": "error", "message": "Missing filename"}), 400
    try:
        playlists.add_track(playlist_id, filename)
        return jsonify({"status": "ok"})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404


@media.route("/playlists/api/<playlist_id>/tracks/<path:filename>", methods=["DELETE"])
@require_personal_device
def playlists_remove_track(playlist_id, filename):
    try:
        playlists.remove_track(playlist_id, filename)
        return jsonify({"status": "ok"})
    except playlists.PlaylistError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404


def _music_action(fn):
    try:
        fn()
        return jsonify({"status": "ok"})
    except music_player.PlayerError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


def _yield_external_to_local():
    """
    Called right before our own (music-tool) playback starts or
    resumes. If "typical laptop media" (Spotify, a browser tab, etc.,
    via playerctl) is currently playing, pause it so the two don't
    play over each other and our track is clearly the one in focus —
    mirroring what already happens in the other direction (external
    media starting preempts an already-playing local track, handled
    in music_now_playing below).

    Deliberately leaves `_ext_was_playing` alone rather than forcing
    it to False here: the pause command is fire-and-forget and may
    not have taken effect by the time the next /now_playing poll
    reads playerctl's status, so let that poll observe reality on its
    own — forcing it early could make a still-momentarily-playing
    read look like a *fresh* start and immediately stop the local
    track we just started.

    Best-effort: if playerctl isn't available or the pause fails for
    any reason, we still go ahead and play our own track regardless.
    """
    try:
        ext = media_keys.get_status()
    except media_keys.MediaKeyError:
        return
    if ext and ext.get("playing"):
        try:
            media_keys.pause()
        except media_keys.MediaKeyError:
            pass
