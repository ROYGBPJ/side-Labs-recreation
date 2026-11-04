import functools
import http.server
import subprocess
import threading
from pathlib import Path

import pytest
from PIL import Image

from server.app import create_app


@pytest.fixture(scope="session")
def media_server(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "sample.mp4")], check=True)
    for i, colour in enumerate(["red", "green", "blue"], 1):
        Image.new("RGB", (64, 64), colour).save(d / f"p{i}.jpg")
    Image.new("RGB", (16, 16), "black").save(d / "site-logo.png")
    (d / "product.html").write_text(
        '<html><head><meta property="og:image" content="/p1.jpg"></head><body>'
        '<img src="/p2.jpg"><img src="/p1.jpg"><img src="/site-logo.png">'
        '<script>var d={"images":["http:\\u002F\\u002F127.0.0.1:PORT\\u002Fp3.jpg"]}</script></body></html>')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    p = d / "product.html"
    p.write_text(p.read_text().replace("PORT", str(port)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True, "DOWNLOAD_DIR": str(tmp_path / "files"),
        "ALLOW_PRIVATE_URLS": True, "IMAGE_PAGE_HOSTS": ["*"], "SITE_URL": "http://testserver",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def strict_client(tmp_path):
    """Default security settings (private addresses blocked, TikTok-only page hosts)."""
    return create_app({"TESTING": True, "DOWNLOAD_DIR": str(tmp_path / "sf")}).test_client()
