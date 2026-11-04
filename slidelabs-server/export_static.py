"""Render the whole site to a folder that works when index.html is double-clicked (no server)."""
import re
import shutil
import sys
import tempfile
from pathlib import Path

from server.app import TOOLS, create_app
from server.blog_data import POSTS

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
PAGES = ["/", "/how-it-works", "/en/blog"] + [f"/tools/{t['slug']}" for t in TOOLS] + [f"/en/blog/{p['slug']}" for p in POSTS]


def rel(target: str, depth: int) -> str:
    prefix = "../" * depth if depth else "./"
    path, sep, frag = target.partition("#")
    path, _, query = path.partition("?")
    if path.startswith("/static/"):
        out = prefix + path[1:]
    elif path == "/":
        out = prefix + "index.html"
    else:
        out = prefix + path.strip("/") + "/index.html"
    return out + (sep + frag if sep else "")


def rewrite(html: str, depth: int) -> str:
    html = re.sub(r'\s*<link rel="canonical"[^>]*>', "", html)
    html = re.sub(r'(\s(?:href|src))="(/[^"/][^"]*|/)"', lambda m: f'{m.group(1)}="{rel(m.group(2), depth)}"', html)
    return html


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    tmp = Path(tempfile.mkdtemp())
    app = create_app({"STATIC_EXPORT": True, "DOWNLOAD_DIR": str(tmp), "SITE_URL": "http://localhost"})
    client = app.test_client()
    for page in PAGES:
        r = client.get(page)
        assert r.status_code == 200, page
        dest = OUT / ("index.html" if page == "/" else page.strip("/") + "/index.html")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rewrite(r.get_data(as_text=True), 0 if page == "/" else page.strip("/").count("/") + 1), encoding="utf-8")
    shutil.copytree(app.static_folder, OUT / "static", ignore=shutil.ignore_patterns("js/tools.js"))
    (OUT / "404.html").write_text(rewrite(client.get("/nope").get_data(as_text=True), 0), encoding="utf-8")
    print(f"exported {len(PAGES)} pages to {OUT}")


if __name__ == "__main__":
    main()
