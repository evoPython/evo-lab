import os
import shutil

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class MusicSearchError(Exception):
    pass


def _ensure_available():
    if yt_dlp is None:
        raise MusicSearchError("yt-dlp not installed (pip install yt-dlp)")
    if shutil.which("ffmpeg") is None:
        raise MusicSearchError("ffmpeg not found (needed to extract mp3 audio)")


def search(query, limit=8):
    """
    Search YouTube for `query` using yt-dlp's own search extractor
    (no need for a separate requests/BeautifulSoup scrape — yt-dlp
    already knows how to turn a query into a list of video results).
    Returns lightweight dicts, nothing is downloaded here.
    """
    if yt_dlp is None:
        raise MusicSearchError("yt-dlp not installed (pip install yt-dlp)")

    if not query or not query.strip():
        return []

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except Exception as exc:
        raise MusicSearchError(str(exc))

    entries = (info or {}).get("entries") or []
    results = []
    for e in entries:
        if not e:
            continue
        thumb = e.get("thumbnail")
        if not thumb and e.get("thumbnails"):
            thumb = e["thumbnails"][-1].get("url")
        results.append({
            "id": e.get("id"),
            "title": e.get("title") or "Untitled",
            "uploader": e.get("uploader") or e.get("channel"),
            "duration": e.get("duration"),
            "thumbnail": thumb,
            "url": f"https://www.youtube.com/watch?v={e.get('id')}",
        })
    return results


def download_mp3(video_id_or_url, music_dir, progress_cb=None):
    """
    Downloads a single video's audio and transcodes it to mp3 with
    ffmpeg (via yt-dlp's postprocessor) directly into the library
    folder. Returns metadata for music_library.add_entry().

    If given, `progress_cb` is passed straight through to yt-dlp as a
    progress hook — called repeatedly with dicts like
    {"status": "downloading", "downloaded_bytes": ..., "total_bytes"
    (or "total_bytes_estimate"): ..., "speed": ...}, then once more
    with {"status": "finished"} when the raw download completes and
    ffmpeg extraction begins.
    """
    _ensure_available()

    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    outtmpl = os.path.join(music_dir, "%(title)s.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    if progress_cb is not None:
        opts["progress_hooks"] = [progress_cb]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)
    except Exception as exc:
        raise MusicSearchError(str(exc))

    mp3_path = os.path.splitext(raw_path)[0] + ".mp3"
    if not os.path.isfile(mp3_path):
        raise MusicSearchError("Download finished but mp3 file wasn't found")

    filename = os.path.basename(mp3_path)
    thumb = info.get("thumbnail")

    return {
        "filename": filename,
        "meta": {
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": thumb,
            "source_url": info.get("webpage_url") or url,
        },
    }
