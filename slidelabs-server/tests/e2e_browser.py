"""Browser checks (Playwright + system Chrome). Run: python tests/e2e_browser.py"""
import functools, http.server, subprocess, sys, tempfile, threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.app import create_app
from server.blog_data import POSTS

tmp = Path(tempfile.mkdtemp())
subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp / "sample.mp4")], check=True)
for n, c in (("p1", "red"), ("p2", "green")):
    Image.new("RGB", (64, 64), c).save(tmp / f"{n}.jpg")
(tmp / "product.html").write_text('<img src="/p1.jpg"><img src="/p2.jpg">')
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp)); h.log_message = lambda *a, **k: None
media = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=media.serve_forever, daemon=True).start()
M = f"http://127.0.0.1:{media.server_address[1]}"
prs = Presentation()
for i in range(2):
    s = prs.slides.add_slide(prs.slide_layouts[6]); w = s.shapes.add_textbox(Inches(8), Inches(7), Inches(1.5), Inches(0.4)); w.text_frame.text = "NotebookLM"
prs.save(tmp / "deck.pptx")

app = create_app({"DOWNLOAD_DIR": str(tmp / "f"), "ALLOW_PRIVATE_URLS": True, "IMAGE_PAGE_HOSTS": ["*"], "SITE_URL": "http://127.0.0.1:5055"})
srv = make_server("127.0.0.1", 5055, app, threaded=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5055"
pages = ["/", "/how-it-works", "/en/blog"] + [f"/tools/{s}" for s in ("video-downloader", "tiktok-image-downloader", "notebooklm-watermark-remover")] + [f"/en/blog/{p['slug']}" for p in POSTS]
fails = []

def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for name, w, hgt in (("mobile", 375, 800), ("tablet", 768, 1024), ("desktop", 1280, 800)):
        ctx = br.new_context(viewport={"width": w, "height": hgt}); pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("requestfailed", lambda r: errs.append("failed " + r.url))
        pg.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        bad = []
        for path in pages:
            pg.goto(B + path, wait_until="networkidle")
            if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"): bad.append(path)
        check(not bad, f"{name} {w}px: no horizontal overflow on {len(pages)} pages {bad}")
        check(not errs, f"{name}: no console/network errors {errs[:3]}")
        if name == "mobile":
            pg.goto(B + "/"); pg.click(".nav-toggle")
            check(pg.is_visible("#nav-menu a[href='/how-it-works']"), "mobile menu opens")
            pg.click(".dropdown-btn"); check(pg.is_visible("a[href='/tools/video-downloader']"), "mobile tools dropdown opens")
            pg.screenshot(path=str(tmp / "mobile-home.png"))
        if name == "desktop":
            pg.goto(B + "/"); pg.click(".dropdown-btn")
            check(pg.is_visible(".dropdown-list a[href='/tools/tiktok-image-downloader']"), "desktop dropdown opens")
            pg.screenshot(path=str(tmp / "desktop-home.png"))
        ctx.close()

    ctx = br.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True); pg = ctx.new_page()
    # video
    pg.goto(B + "/tools/video-downloader"); pg.fill("#url", M + "/sample.mp4"); pg.click("#submit")
    pg.wait_for_selector("#error:not([hidden])"); check("Confirm" in pg.inner_text("#error"), "video: rights required")
    pg.check("#rights"); pg.click("#submit"); pg.wait_for_selector("#quality", timeout=30000)
    pg.click(".vid-actions button"); pg.wait_for_selector(".result-card a.btn:has-text('Save ')", timeout=60000)
    with pg.expect_download() as d: pg.click(".result-card a.btn:has-text('Save ')")
    check(Path(d.value.path()).stat().st_size > 1000, "video: info -> download -> file saved")
    # images
    pg.goto(B + "/tools/tiktok-image-downloader"); pg.fill("#url", M + "/product.html"); pg.check("#rights"); pg.click("#submit")
    pg.wait_for_selector(".img-item", timeout=15000)
    check(pg.locator(".img-item").count() == 2 and pg.evaluate("[...document.images].filter(i=>i.closest('.img-item')).every(i=>i.naturalWidth>0)"), "images: 2 thumbnails load")
    with pg.expect_download() as d: pg.click("text=Download selected as ZIP")
    check(d.value.suggested_filename == "product-images.zip", "images: ZIP downloads")
    # watermark
    pg.goto(B + "/tools/notebooklm-watermark-remover"); pg.set_input_files("#file", str(tmp / "deck.pptx")); pg.check("#rights"); pg.click("#submit")
    pg.wait_for_selector(".result-card a", timeout=15000)
    check("Removed 2" in pg.inner_text("#result"), "watermark: result shown")
    with pg.expect_download() as d: pg.click(".result-card a")
    check(d.value.suggested_filename == "deck-clean.pptx", "watermark: cleaned file downloads")
    br.close()

print("\nFAILED:" if fails else "\nALL BROWSER CHECKS PASSED", fails or "")
print("screenshots:", tmp)
sys.exit(1 if fails else 0)
