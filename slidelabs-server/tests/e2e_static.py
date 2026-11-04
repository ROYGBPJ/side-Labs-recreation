"""Checks the static export from file:// (no server). Run: python export_static.py dist && python tests/e2e_static.py dist"""
import functools, http.server, re, subprocess, sys, tempfile, threading, zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
from playwright.sync_api import sync_playwright
from pptx import Presentation
from pptx.util import Inches

dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
tmp = Path(tempfile.mkdtemp())
fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

# ---- static link/asset check (no browser)
class L(HTMLParser):
    def __init__(s): super().__init__(); s.r = []
    def handle_starttag(s, t, a):
        for k, v in a:
            if k in ("href", "src") and v: s.r.append(v)
pages = sorted(dist.rglob("index.html"))
broken = []
for pg in pages:
    p = L(); p.feed(pg.read_text(encoding="utf-8"))
    for ref in p.r:
        if ref.startswith(("http", "#", "data:", "mailto:")): continue
        if not (pg.parent / unquote(ref.split("#")[0])).resolve().exists(): broken.append((pg.relative_to(dist).as_posix(), ref))
check(len(pages) == 17, f"17 exported pages ({len(pages)})")
check(not broken, f"all relative links/assets resolve {broken[:3]}")
check(not any("/pricing" in pg.read_text() or "login" in pg.read_text().lower().replace("login-only", "") for pg in pages), "no pricing/login references")
check(all('href="/' not in pg.read_text() and 'src="/' not in pg.read_text() for pg in pages), "no root-absolute URLs (works on file://)")

# ---- fixtures: CORS-enabled media server
subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10", "-pix_fmt", "yuv420p", str(tmp / "sample.mp4")], check=True)
for n, c in (("p1", "red"), ("p2", "green")): Image.new("RGB", (64, 64), c).save(tmp / f"{n}.jpg")
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self): self.send_header("Access-Control-Allow-Origin", "*"); super().end_headers()
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(tmp))); threading.Thread(target=srv.serve_forever, daemon=True).start()
M = f"http://127.0.0.1:{srv.server_address[1]}"
prs = Presentation()
for i in range(3):
    s = prs.slides.add_slide(prs.slide_layouts[6]); s.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text_frame.text = f"Slide {i}"
    s.shapes.add_textbox(Inches(8), Inches(7), Inches(1.5), Inches(0.4)).text_frame.text = "NotebookLM"
    s.shapes.add_picture(str(tmp / "p1.jpg"), Inches(8.8), Inches(7), Inches(0.5), Inches(0.5))   # repeated corner logo
prs.save(tmp / "deck.pptx")
plain = Presentation(); plain.slides.add_slide(plain.slide_layouts[6]).shapes.add_textbox(0, 0, Inches(2), Inches(1)).text_frame.text = "hi"; plain.save(tmp / "plain.pptx")

site = [p for p in pages]
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for name, w in (("mobile", 375), ("desktop", 1280)):
        ctx = br.new_context(viewport={"width": w, "height": 800}); pg = ctx.new_page(); errs = []; bad = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("requestfailed", lambda r: errs.append("failed " + r.url))
        for f in site:
            pg.goto(f.as_uri(), wait_until="load")
            if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"): bad.append(f.relative_to(dist).as_posix())
        check(not bad, f"{name}: no overflow on 17 file:// pages {bad}")
        check(not errs, f"{name}: no console/network errors {errs[:3]}")
        ctx.close()
    ctx = br.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # navigation by clicking through file:// links
    pg.goto((dist / "index.html").as_uri()); pg.click(".dropdown-btn"); pg.click("text=Video Downloader >> nth=0")
    check(pg.url.endswith("tools/video-downloader/index.html") and "Video Downloader" in pg.inner_text("h1"), "nav: dropdown -> tool page")
    pg.click(".brand >> nth=0"); check(pg.url.endswith("/index.html") and "tools" not in pg.url, "nav: logo -> home")
    pg.click("a:has-text('Blog') >> nth=0"); pg.click(".card-link >> nth=0"); check("/en/blog/" in pg.url and pg.locator("article h1").count() == 1, "nav: blog -> article")
    # video
    pg.goto((dist / "tools/video-downloader/index.html").as_uri()); pg.fill("#url", M + "/sample.mp4"); pg.click("#submit")
    check("Confirm" in (pg.inner_text("#error") if pg.is_visible("#error") else ""), "video: rights required")
    pg.check("#rights")
    with pg.expect_download(timeout=15000) as d: pg.click("#submit")
    check(d.value.suggested_filename == "sample.mp4" and Path(d.value.path()).stat().st_size > 500, "video: direct link downloads")
    pg.fill("#url", "http://127.0.0.1:9/none.mp4"); pg.click("#submit"); pg.wait_for_selector("#error:not([hidden])")
    check("server" in pg.inner_text("#error").lower(), "video: blocked/unreachable link shows clear message")
    # images: pasted source + image list
    pg.goto((dist / "tools/tiktok-image-downloader/index.html").as_uri())
    html = f'<meta property="og:image" content="{M}/p1.jpg"><img src="{M}/p2.jpg"><img src="{M}/p1.jpg"><img src="{M}/site-logo.png">'
    pg.fill("#url", html); pg.check("#rights"); pg.click("#submit"); pg.wait_for_selector(".img-item")
    check(pg.locator(".img-item").count() == 2 and pg.evaluate("[...document.querySelectorAll('.img-item img')].every(i=>i.naturalWidth>0)"), "images: pasted source -> 2 thumbnails")
    with pg.expect_download(timeout=15000) as d: pg.click("text=Download selected as ZIP")
    names = zipfile.ZipFile(d.value.path()).namelist()
    check(d.value.suggested_filename == "product-images.zip" and len(names) == 2, f"images: ZIP built in browser {names}")
    with pg.expect_download(timeout=15000) as d: pg.click(".img-item a >> nth=0")
    check(d.value.suggested_filename.startswith("product-image-1"), "images: single download")
    pg.fill("#url", "https://www.tiktok.com/view/product/123"); pg.click("#submit"); pg.wait_for_selector("#error:not([hidden])", timeout=20000)
    check("page source" in pg.inner_text("#error"), "images: blocked page link explains paste-source fallback")
    # watermark
    pg.goto((dist / "tools/notebooklm-watermark-remover/index.html").as_uri())
    pg.set_input_files("#file", str(tmp / "deck.pptx")); pg.check("#rights"); pg.click("#submit"); pg.wait_for_selector(".result-card a")
    check("Removed 6" in pg.inner_text("#result"), "watermark: removed 3 text marks + 3 repeated logos -> " + pg.inner_text("#result").split("\n")[1])
    with pg.expect_download() as d: pg.click(".result-card a")
    out = Presentation(d.value.path()); left = [sh.text_frame.text for s in out.slides for sh in s.shapes if sh.has_text_frame]
    pics = sum(1 for s in out.slides for sh in s.shapes if sh.shape_type == 13)
    check(d.value.suggested_filename == "deck-clean.pptx" and "NotebookLM" not in left and len(left) == 3 and pics == 0, f"watermark: cleaned file valid in python-pptx (texts={left}, pics={pics})")
    pg.set_input_files("#file", str(tmp / "plain.pptx")); pg.click("#submit"); pg.wait_for_selector("#error:not([hidden])")
    check("No NotebookLM watermark" in pg.inner_text("#error"), "watermark: clean file reports nothing found")
    pdf = tmp / "x.pdf"; pdf.write_bytes(b"%PDF-1.4"); pg.set_input_files("#file", str(pdf)); pg.click("#submit")
    check("server" in pg.inner_text("#error").lower(), "watermark: PDF gives clear message")
    check(not errs, f"tools: no JS errors {errs}")
    br.close()
print("\nFAILED" if fails else "\nALL STATIC CHECKS PASSED", fails or "")
sys.exit(1 if fails else 0)
