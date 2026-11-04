"""NotebookLM watermark remover. Reimplemented.

Detection is heuristic and was built without access to a real NotebookLM export:
  * text containing "NotebookLM" is removed (PPTX shapes incl. layouts/master; PDF text via redaction)
  * small pictures in the bottom-right corner that repeat on at least half the pages/slides are removed
A watermark baked into a full-page raster image is NOT detected; in that case the tool
reports "no watermark found" instead of pretending to succeed.
"""
import hashlib
import math
import shutil
from pathlib import Path

import pymupdf
from flask import Blueprint, current_app, jsonify, request
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from werkzeug.utils import secure_filename

from .storage import new_job_dir

bp = Blueprint("watermark", __name__)
NEEDLE = "notebooklm"


class NothingFound(Exception):
    pass


# ---------- PPTX ----------
def _walk(shapes):
    for sh in shapes:
        yield sh
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _walk(sh.shapes)


def _has_needle(sh) -> bool:
    return sh.has_text_frame and NEEDLE in sh.text_frame.text.lower()


def _corner_pic(sh, sw, sh_h) -> bool:
    if sh.shape_type != MSO_SHAPE_TYPE.PICTURE or None in (sh.left, sh.top, sh.width, sh.height):
        return False
    small = sh.width * sh.height < 0.06 * sw * sh_h
    return small and (sh.left + sh.width / 2) > 0.6 * sw and (sh.top + sh.height / 2) > 0.8 * sh_h


def clean_pptx(src: Path, dst: Path) -> int:
    prs = Presentation(str(src))
    sw, shh = prs.slide_width, prs.slide_height
    slides = list(prs.slides)
    counts: dict[str, int] = {}
    for s in slides:
        seen = set()
        for sh in _walk(s.shapes):
            if _corner_pic(sh, sw, shh):
                seen.add(hashlib.sha1(sh.image.blob).hexdigest())
        for h in seen:
            counts[h] = counts.get(h, 0) + 1
    threshold = max(2, math.ceil(len(slides) / 2))
    repeated = {h for h, c in counts.items() if c >= threshold}

    removed = 0
    containers = []
    for s in slides:
        containers.append(s.shapes)
    for layout in {id(s.slide_layout): s.slide_layout for s in slides}.values():
        containers.append(layout.shapes)
    for master in {id(s.slide_layout.slide_master): s.slide_layout.slide_master for s in slides}.values():
        containers.append(master.shapes)
    for shapes in containers:
        for sh in list(_walk(shapes)):
            hit = _has_needle(sh) or (_corner_pic(sh, sw, shh) and hashlib.sha1(sh.image.blob).hexdigest() in repeated)
            if hit:
                el = sh._element
                el.getparent().remove(el)
                removed += 1
    if not removed:
        raise NothingFound()
    prs.save(str(dst))
    return removed


# ---------- PDF ----------
def _fill_colour(pix, rect):
    pts = [(rect.x0 - 3, rect.y0 - 3), (rect.x1 + 3, rect.y0 - 3), (rect.x0 - 3, rect.y1 + 3), (rect.x1 + 3, rect.y1 + 3)]
    samples = []
    for x, y in pts:
        x, y = int(min(max(x, 0), pix.width - 1)), int(min(max(y, 0), pix.height - 1))
        samples.append(pix.pixel(x, y)[:3])
    return tuple(sorted(sm[i] for sm in samples)[len(samples) // 2] / 255 for i in range(3))


def clean_pdf(src: Path, dst: Path) -> int:
    doc = pymupdf.open(str(src))
    n = len(doc)
    counts: dict[str, int] = {}
    page_imgs = []
    for page in doc:
        W, H = page.rect.width, page.rect.height
        cands = []
        for info in page.get_image_info(xrefs=True):
            r = pymupdf.Rect(info["bbox"])
            if not info.get("xref") or r.is_empty:
                continue
            if r.width * r.height < 0.06 * W * H and r.x0 + r.width / 2 > 0.6 * W and r.y0 + r.height / 2 > 0.8 * H:
                h = hashlib.sha1(doc.extract_image(info["xref"])["image"]).hexdigest()
                cands.append((h, r))
        page_imgs.append(cands)
        for h in {h for h, _ in cands}:
            counts[h] = counts.get(h, 0) + 1
    threshold = max(2, math.ceil(n / 2))
    removed = 0
    for page, cands in zip(doc, page_imgs):
        rects = [r for r in page.search_for("NotebookLM")]
        rects += [r for h, r in cands if counts[h] >= threshold]
        if not rects:
            continue
        pix = page.get_pixmap(alpha=False)
        for r in rects:
            rr = r + (-1, -1, 1, 1)
            page.add_redact_annot(rr, fill=_fill_colour(pix, rr))
            removed += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
    if not removed:
        doc.close()
        raise NothingFound()
    doc.save(str(dst), garbage=3, deflate=True)
    doc.close()
    return removed


@bp.post("/api/watermark")
def remove():
    if request.form.get("confirm_rights") != "true":
        return jsonify(error="Confirm that you own this file or have permission to edit it."), 400
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Choose a PPTX or PDF file."), 400
    name = secure_filename(f.filename)
    ext = Path(name).suffix.lower()
    if ext not in (".pptx", ".pdf"):
        return jsonify(error="Only .pptx and .pdf files are supported."), 400
    file_id, folder = new_job_dir()
    src = folder / ("source" + ext)
    f.save(src)
    out_name = f"{Path(name).stem}-clean{ext}"
    dst = folder / out_name
    try:
        removed = clean_pptx(src, dst) if ext == ".pptx" else clean_pdf(src, dst)
    except NothingFound:
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error="No NotebookLM watermark was detected. If it is baked into the slide images, this tool can't remove it."), 422
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        return jsonify(error="This file couldn't be read. Make sure it is a valid, unencrypted export."), 422
    src.unlink(missing_ok=True)
    return jsonify(file_id=file_id, filename=out_name, removed=removed, url=f"/api/files/{file_id}")
