"""Temporary file storage for generated downloads, with time-based cleanup."""
import re
import shutil
import time
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, send_from_directory

bp = Blueprint("files", __name__)
ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_job_dir() -> tuple[str, Path]:
    purge_expired()
    file_id = uuid.uuid4().hex
    d = Path(current_app.config["DOWNLOAD_DIR"]) / file_id
    d.mkdir(parents=True, exist_ok=True)
    return file_id, d


def purge_expired() -> None:
    root = Path(current_app.config["DOWNLOAD_DIR"])
    if not root.exists():
        return
    cutoff = time.time() - current_app.config["FILE_TTL_SECONDS"]
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


@bp.get("/api/files/<file_id>")
def get_file(file_id):
    if not ID_RE.match(file_id):
        abort(404)
    d = Path(current_app.config["DOWNLOAD_DIR"]) / file_id
    files = [p for p in d.iterdir() if p.is_file()] if d.is_dir() else []
    if not files:
        return jsonify(error="This file has expired. Please run the tool again."), 404
    return send_from_directory(d, files[0].name, as_attachment=True)
