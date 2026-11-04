import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pymupdf
import pytest
from pptx import Presentation
from pptx.util import Inches

from server.blog_data import POSTS

PAGES = ["/", "/how-it-works", "/en/blog"] + [f"/tools/{s}" for s in ("video-downloader", "tiktok-image-downloader", "notebooklm-watermark-remover")] + [f"/en/blog/{p['slug']}" for p in POSTS]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k):
                self.refs.append(a[k])


@pytest.mark.parametrize("path", PAGES)
def test_page_loads(client, path):
    r = client.get(path)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<title>" in html and 'name="viewport"' in html and "<h1" in html


def test_page_count_matches_english_inventory():
    assert len(PAGES) == 17 and len(POSTS) == 11


@pytest.mark.parametrize("path", PAGES)
def test_internal_links_and_assets_resolve(client, path):
    p = Links()
    p.feed(client.get(path).get_data(as_text=True))
    for ref in p.refs:
        if ref.startswith(("http", "mailto:", "#", "data:", "//")):
            continue
        r = client.get(ref.split("#")[0])
        assert r.status_code in (200, 302), f"{path} -> {ref} = {r.status_code}"


def test_no_pricing_or_login(client):
    for gone in ("/pricing", "/login", "/account", "/dashboard/", "/api/auth/me"):
        assert client.get(gone).status_code == 404, gone
    for path in PAGES:
        html = client.get(path).get_data(as_text=True)
        assert 'href="/pricing"' not in html and 'href="/login' not in html and "Log in" not in html, path
    assert "/pricing" not in client.get("/sitemap.xml").get_data(as_text=True)
    assert "/pricing" not in client.get("/llms.txt").get_data(as_text=True)


def test_sitemap_robots_llms(client):
    sm = client.get("/sitemap.xml").get_data(as_text=True)
    urls = re.findall(r"<loc>http://testserver(.*?)</loc>", sm)
    assert sorted(urls) == sorted(PAGES)
    assert "Sitemap:" in client.get("/robots.txt").get_data(as_text=True)
    assert "Video Downloader" in client.get("/llms.txt").get_data(as_text=True)


def test_404_html_and_json(client):
    assert client.get("/nope").status_code == 404
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.is_json


# ---- video ----
def test_video_requires_rights_and_valid_url(client):
    assert client.post("/api/video/info", json={"url": "https://x.co/v"}).status_code == 400
    assert client.post("/api/video/info", json={"url": "ftp://x", "confirm_rights": True}).status_code == 400
    assert client.post("/api/video/info", json={"url": "", "confirm_rights": True}).status_code == 400


def test_video_blocks_private_addresses(strict_client):
    r = strict_client.post("/api/video/info", json={"url": "http://127.0.0.1:9/v.mp4", "confirm_rights": True})
    assert r.status_code == 400 and "private" in r.get_json()["error"].lower()


def test_video_info_and_download(client, media_server):
    url = media_server + "/sample.mp4"
    r = client.post("/api/video/info", json={"url": url, "confirm_rights": True})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["title"]
    d = client.post("/api/video/download", json={"url": url, "quality": "best", "confirm_rights": True})
    assert d.status_code == 200, d.get_json()
    f = client.get(d.get_json()["url"])
    assert f.status_code == 200 and len(f.data) > 1000 and "attachment" in f.headers["Content-Disposition"]
    a = client.post("/api/video/download", json={"url": url, "quality": "audio", "confirm_rights": True})
    assert a.status_code == 200 and a.get_json()["filename"].endswith(".mp3")


def test_video_unreachable_gives_clean_error(client, media_server):
    r = client.post("/api/video/info", json={"url": media_server + "/missing.mp4", "confirm_rights": True})
    assert r.status_code == 422 and r.get_json()["error"]


def test_file_endpoint_rejects_bad_ids(client):
    assert client.get("/api/files/../../etc/passwd").status_code == 404
    assert client.get("/api/files/" + "0" * 32).status_code == 404


# ---- images ----
def test_images_extract_download_zip(client, media_server):
    assert client.post("/api/images/extract", json={"url": media_server + "/product.html"}).status_code == 400
    r = client.post("/api/images/extract", json={"url": media_server + "/product.html", "confirm_rights": True})
    assert r.status_code == 200, r.get_json()
    imgs = r.get_json()["images"]
    assert r.get_json()["count"] == 3  # p1 deduped, logo skipped, JSON-embedded p3 found
    one = client.get("/api/images/fetch?download=1&t=" + imgs[0]["token"])
    assert one.status_code == 200 and one.mimetype == "image/jpeg" and "attachment" in one.headers["Content-Disposition"]
    z = client.post("/api/images/zip", json={"tokens": [i["token"] for i in imgs]})
    assert z.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(z.data)).namelist()) == 3
    assert client.get("/api/images/fetch?t=forged").status_code == 400
    assert client.post("/api/images/zip", json={"tokens": []}).status_code == 400


def test_images_host_allowlist(strict_client):
    r = strict_client.post("/api/images/extract", json={"url": "https://example.com/p", "confirm_rights": True})
    assert r.status_code == 400 and "tiktok.com" in r.get_json()["error"]


def test_images_page_without_images(client, media_server, tmp_path):
    r = client.post("/api/images/extract", json={"url": media_server + "/sample.mp4", "confirm_rights": True})
    assert r.status_code == 422


# ---- watermark ----
def _pptx(tmp_path, with_mark=True):
    prs = Presentation()
    for i in range(3):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)); tb.text_frame.text = f"Slide {i}"
        if with_mark:
            w = s.shapes.add_textbox(Inches(8), Inches(7), Inches(1.5), Inches(0.4)); w.text_frame.text = "NotebookLM"
    p = tmp_path / "deck.pptx"; prs.save(p); return p


def _upload(client, path, name=None, rights="true"):
    return client.post("/api/watermark", data={"file": (open(path, "rb"), name or path.name), "confirm_rights": rights}, content_type="multipart/form-data")


def test_watermark_pptx(client, tmp_path):
    r = _upload(client, _pptx(tmp_path))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["removed"] == 3
    out = Presentation(io.BytesIO(client.get(r.get_json()["url"]).data))
    texts = [sh.text_frame.text for s in out.slides for sh in s.shapes if sh.has_text_frame]
    assert "NotebookLM" not in texts and len(texts) == 3


def test_watermark_pptx_nothing_found(client, tmp_path):
    r = _upload(client, _pptx(tmp_path, with_mark=False))
    assert r.status_code == 422 and "No NotebookLM watermark" in r.get_json()["error"]


def test_watermark_pdf(client, tmp_path):
    doc = pymupdf.open()
    for i in range(2):
        pg = doc.new_page(); pg.insert_text((72, 100), f"Page {i}"); pg.insert_text((480, 820), "NotebookLM", fontsize=10)
    p = tmp_path / "x.pdf"; doc.save(p)
    r = _upload(client, p)
    assert r.status_code == 200, r.get_json()
    out = pymupdf.open(stream=client.get(r.get_json()["url"]).data, filetype="pdf")
    txt = "".join(pg.get_text() for pg in out)
    assert "NotebookLM" not in txt and "Page 0" in txt and "Page 1" in txt


def test_watermark_validation(client, tmp_path):
    p = _pptx(tmp_path)
    assert _upload(client, p, rights="false").status_code == 400
    bad = tmp_path / "x.txt"; bad.write_text("hi")
    assert _upload(client, bad).status_code == 400
    corrupt = tmp_path / "c.pdf"; corrupt.write_text("not a pdf")
    assert _upload(client, corrupt).status_code == 422
    assert client.post("/api/watermark", data={"confirm_rights": "true"}, content_type="multipart/form-data").status_code == 400


def test_error_messages_are_clean():
    from server.downloader import _clean_error
    raw = "\x1b[0;31mERROR:\x1b[0m [TikTok] 1: Unexpected response from webpage request; please report this issue"
    out = _clean_error(Exception(raw))
    assert "\x1b" not in out and "[0;31m" not in out and "please report" not in out and "refused" in out
    assert "[0;31m" not in _clean_error(Exception("[0;31mERROR:[0m something odd"))
