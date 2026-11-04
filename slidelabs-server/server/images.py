"""TikTok Shop product-image extractor. Reimplemented from the public description in llms.txt.

Extraction heuristics (og:image, <img>, image URLs inside embedded JSON) are
inferred and have not been verified against live TikTok pages.
"""
import io
import json
import re
import zipfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Blueprint, Response, current_app, jsonify, request
from itsdangerous import BadSignature, URLSafeSerializer

from .security import UrlRejected, validate_public_url

bp = Blueprint("images", __name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; SlideLabsImageTool/1.0)"}
IMG_RE = re.compile(r"https?://[^\"'\s<>\\]+?\.(?:jpe?g|png|webp)(?:[~?][^\"'\s<>\\]*)?", re.I)
SKIP = ("avatar", "logo", "icon", "emoji", "sprite", "favicon")
MAX_IMAGES = 60
MAX_IMG_BYTES = 15 * 1024 * 1024
RIGHTS_MSG = "Confirm that you own these images or have permission to download them."


def _signer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="img-token")


def _safe_get(url, page_check, stream=False):
    allow_private = current_app.config["ALLOW_PRIVATE_URLS"]
    allow = current_app.config["IMAGE_PAGE_HOSTS"] if page_check else None
    for _ in range(5):
        validate_public_url(url, allow_private, allow)
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=False, stream=stream)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            continue
        return r
    raise UrlRejected("Too many redirects.")


def extract_image_urls(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for tag in soup.find_all("meta", attrs={"property": "og:image"}):
        if tag.get("content"):
            found.append(urljoin(base, tag["content"]))
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and not src.startswith("data:"):
            found.append(urljoin(base, src))
    blob = html.replace("\\u002F", "/").replace("\\/", "/")
    found.extend(IMG_RE.findall(blob))
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            found.extend(IMG_RE.findall(json.dumps(json.loads(script.string or ""))))
        except ValueError:
            pass
    best: dict[str, str] = {}
    for u in found:
        if any(s in u.lower() for s in SKIP):
            continue
        key = re.split(r"[~?]", u, maxsplit=1)[0]
        if key not in best or len(u) < len(best[key]):
            best[key] = u
    return list(best.values())[:MAX_IMAGES]


@bp.post("/api/images/extract")
def extract():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON body."), 400
    if data.get("confirm_rights") is not True:
        return jsonify(error=RIGHTS_MSG), 400
    try:
        r = _safe_get(str(data.get("url", "")), page_check=True)
    except UrlRejected as e:
        return jsonify(error=str(e)), 400
    except requests.RequestException:
        return jsonify(error="Could not load that page. Check the link and try again."), 422
    if r.status_code != 200:
        return jsonify(error=f"The page returned status {r.status_code}."), 422
    urls = extract_image_urls(r.text, r.url)
    if not urls:
        return jsonify(error="No product images were found on that page."), 422
    s = _signer()
    return jsonify(images=[{"token": s.dumps(u), "host": urlparse(u).hostname} for u in urls], count=len(urls))


def _fetch_image(token: str):
    try:
        url = _signer().loads(token)
    except BadSignature:
        raise UrlRejected("Invalid image reference.")
    r = _safe_get(url, page_check=False, stream=True)
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip()
    if r.status_code != 200 or not ctype.startswith("image/"):
        raise UrlRejected("That image could not be loaded.")
    body = r.raw.read(MAX_IMG_BYTES + 1, decode_content=True)
    if len(body) > MAX_IMG_BYTES:
        raise UrlRejected("Image is too large.")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(ctype, "img")
    return body, ctype, ext


@bp.get("/api/images/fetch")
def fetch_one():
    token = request.args.get("t", "")
    try:
        body, ctype, ext = _fetch_image(token)
    except UrlRejected as e:
        return jsonify(error=str(e)), 400
    except requests.RequestException:
        return jsonify(error="That image could not be loaded."), 422
    disp = "attachment" if request.args.get("download") == "1" else "inline"
    return Response(body, mimetype=ctype, headers={"Content-Disposition": f'{disp}; filename="product-image.{ext}"', "Cache-Control": "private, max-age=600"})


@bp.post("/api/images/zip")
def zip_images():
    data = request.get_json(silent=True)
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if not isinstance(tokens, list) or not tokens or len(tokens) > MAX_IMAGES:
        return jsonify(error="Select between 1 and 60 images."), 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, t in enumerate(tokens, 1):
            try:
                body, _c, ext = _fetch_image(str(t))
            except (UrlRejected, requests.RequestException):
                continue
            z.writestr(f"product-image-{i:02d}.{ext}", body)
        if not z.namelist():
            return jsonify(error="None of the selected images could be downloaded."), 422
    return Response(buf.getvalue(), mimetype="application/zip", headers={"Content-Disposition": 'attachment; filename="product-images.zip"'})
