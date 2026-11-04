"""Video downloader backed by yt-dlp. Reimplemented; not the original service.

Only works for content the requester is authorised to download. DRM-protected
formats are never requested (allow_unplayable_formats stays False) and no
cookies/credentials are accepted.
"""
import re
import shutil
import threading

import yt_dlp
from flask import Blueprint, current_app, jsonify, request

from .security import UrlRejected, validate_public_url
from .storage import new_job_dir

bp = Blueprint("video", __name__)
_slots = threading.BoundedSemaphore(2)
RIGHTS_MSG = "Confirm that you own this content or have permission to download it."


ANSI = re.compile(r"\x1b\[[0-9;]*m|\[\d+(?:;\d+)*m")


def _impersonate():
    """Browser-like TLS fingerprint (needs curl-cffi). TikTok rejects plain Python requests."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        return ImpersonateTarget("chrome")
    except Exception:
        return None


def _base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "ignoreconfig": True,
        "allow_unplayable_formats": False,
        "max_filesize": current_app.config["MAX_DOWNLOAD_MB"] * 1024 * 1024,
        "color": {"stdout": "never", "stderr": "never"},
    }
    target = _impersonate()
    if target is not None:
        opts["impersonate"] = target
    return opts


def _check(data):
    if not isinstance(data, dict):
        raise UrlRejected("Send a JSON body.")
    if data.get("confirm_rights") is not True:
        raise UrlRejected(RIGHTS_MSG)
    return validate_public_url(data.get("url"), current_app.config["ALLOW_PRIVATE_URLS"])


def _clean_error(exc: Exception) -> str:
    msg = ANSI.sub("", str(exc))
    msg = msg.replace("ERROR: ", "").split("\n")[0].strip()
    if "Unexpected response from webpage request" in msg or "Unable to extract" in msg or "HTTP Error 403" in msg:
        return ("The site refused the request. TikTok and some other platforms block automated downloads, "
                "especially from hosting servers, so this link can't be fetched from here. "
                "Try again later, or use a direct video file link.")
    if "DRM" in msg.upper():
        return "This video is DRM-protected and cannot be downloaded."
    if "Unsupported URL" in msg:
        return "This link isn't supported or doesn't point to a downloadable video."
    return msg[:300] or "Could not read that link."


@bp.post("/api/video/info")
def info():
    try:
        url = _check(request.get_json(silent=True))
    except UrlRejected as e:
        return jsonify(error=str(e)), 400
    try:
        with yt_dlp.YoutubeDL(_base_opts()) as ydl:
            meta = ydl.extract_info(url, download=False)
    except Exception as e:  # yt-dlp raises many error types
        return jsonify(error=_clean_error(e)), 422
    if meta.get("_type") == "playlist" and meta.get("entries"):
        meta = next((e for e in meta["entries"] if e), meta)
    formats = meta.get("formats") or []
    heights = sorted({f["height"] for f in formats if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
    has_video = bool(heights) or any(f.get("vcodec") not in (None, "none") for f in formats)
    return jsonify(
        title=meta.get("title") or "Untitled video",
        thumbnail=meta.get("thumbnail"),
        duration=meta.get("duration"),
        uploader=meta.get("uploader"),
        site=meta.get("extractor_key"),
        heights=heights,
        has_video=has_video,
    )


@bp.post("/api/video/download")
def download():
    data = request.get_json(silent=True)
    try:
        url = _check(data)
    except UrlRejected as e:
        return jsonify(error=str(e)), 400
    quality = str(data.get("quality", "best"))
    has_ffmpeg = shutil.which("ffmpeg") is not None
    opts = _base_opts()
    if quality == "audio":
        opts["format"] = "ba/b"
        if has_ffmpeg:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    elif quality.isdigit():
        h = int(quality)
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/b" if has_ffmpeg else f"b[height<={h}]/b"
    else:
        opts["format"] = "bv*+ba/b" if has_ffmpeg else "b"
    if has_ffmpeg:
        opts["merge_output_format"] = "mp4"

    if not _slots.acquire(blocking=False):
        return jsonify(error="The server is busy with other downloads. Try again in a moment."), 429
    file_id, folder = new_job_dir()
    try:
        opts["outtmpl"] = str(folder / "%(title).80s.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error=_clean_error(e)), 422
    finally:
        _slots.release()
    files = [p for p in folder.iterdir() if p.is_file()]
    if not files:
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error="Nothing was downloaded (the file may exceed the size limit)."), 422
    f = max(files, key=lambda p: p.stat().st_size)
    return jsonify(file_id=file_id, filename=f.name, size=f.stat().st_size, url=f"/api/files/{file_id}")
