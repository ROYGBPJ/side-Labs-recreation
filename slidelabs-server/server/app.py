from pathlib import Path
from xml.sax.saxutils import escape

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

from . import downloader, images, storage, watermark
from .blog_data import DATE, POSTS
from .config import load_config

TOOLS = [
    {
        "slug": "video-downloader",
        "name": "Video Downloader",
        "tagline": "Download videos from TikTok, YouTube, Instagram, Facebook, Douyin, bilibili, X, Threads and 1,600+ other sites in HD.",
        "short": "Save videos in HD from 1,600+ sites. Free, no app, no sign-up.",
    },
    {
        "slug": "tiktok-image-downloader",
        "name": "TikTok Shop Image Downloader",
        "tagline": "Paste a TikTok Shop product link to download all product images, as single files or one ZIP.",
        "short": "Grab every product photo from a TikTok Shop listing. Free, no sign-up.",
    },
    {
        "slug": "notebooklm-watermark-remover",
        "name": "NotebookLM Watermark Remover",
        "tagline": "Upload a NotebookLM slide export (PPTX or PDF) and download it without the watermark.",
        "short": "Clean NotebookLM exports in PPTX or PDF. Free, no sign-up.",
    },
]

PRODUCTS = [
    ("AI Visual Studio", "Create marketing visuals, ad directions, thumbnails and creative variations from references."),
    ("Campaign Kit Generator", "Turn a product, client or creator brief into campaign angles, messages, scripts, captions and activation ideas."),
    ("Trend Research AI", "Discover rising content signals and convert them into useful marketing angles."),
    ("KOL Matching", "Build UGC, KOC and KOL shortlists by platform role, audience fit, niche, content style and campaign goal."),
    ("Content Factory", "Produce repeatable content calendars, hooks, captions, scripts and publishing rhythms."),
    ("Slide Replicator", "Adapt successful campaign structures across brands, markets, products and creator activations."),
]

STATIC_PAGES = ["/", "/how-it-works", "/en/blog"]


def create_app(overrides=None) -> Flask:
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / "templates"), static_folder=str(root / "static"))
    app.config.update(load_config(overrides))
    Path(app.config["DOWNLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    for mod in (downloader, images, watermark, storage):
        app.register_blueprint(mod.bp)

    posts = {p["slug"]: p for p in POSTS}

    @app.context_processor
    def inject():
        return {"static_export": bool(app.config.get("STATIC_EXPORT")), "tools": TOOLS, "site_url": app.config["SITE_URL"].rstrip("/"), "request_path": request.path}

    # ----- pages -----
    @app.get("/")
    def home():
        return render_template("index.html", products=PRODUCTS, latest=POSTS[:3])

    @app.get("/how-it-works")
    def how_it_works():
        return render_template("how_it_works.html", products=PRODUCTS)

    @app.get("/tools/<slug>")
    def tool(slug):
        t = next((t for t in TOOLS if t["slug"] == slug), None)
        if not t:
            abort(404)
        return render_template(f"tool_{slug.replace('-', '_')}.html", tool=t)

    @app.get("/en/blog")
    def blog_index():
        return render_template("blog_index.html", posts=POSTS, date=DATE)

    @app.get("/en/blog/<slug>")
    def blog_post(slug):
        post = posts.get(slug)
        if not post:
            abort(404)
        others = [p for p in POSTS if p["slug"] != slug][:3]
        return render_template("blog_post.html", post=post, date=DATE, others=others)

    @app.get("/en")
    @app.get("/en/")
    def en_root():
        return redirect("/")

    # ----- crawler files -----
    @app.get("/sitemap.xml")
    def sitemap():
        base = app.config["SITE_URL"].rstrip("/")
        urls = STATIC_PAGES + [f"/tools/{t['slug']}" for t in TOOLS] + [f"/en/blog/{p['slug']}" for p in POSTS]
        body = "".join(f"<url><loc>{escape(base + u)}</loc></url>" for u in urls)
        xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
        return Response(xml, mimetype="application/xml")

    @app.get("/robots.txt")
    def robots():
        base = app.config["SITE_URL"].rstrip("/")
        txt = f"User-agent: *\nAllow: /\nAllow: /en/blog/\nAllow: /llms.txt\nDisallow: /api/\n\nSitemap: {base}/sitemap.xml\n"
        return Response(txt, mimetype="text/plain")

    @app.get("/llms.txt")
    def llms():
        base = app.config["SITE_URL"].rstrip("/")
        lines = ["# SlideLabs", "", "> An outcome-driven AI marketing workspace for agencies, creators and brand teams.", "", "## Site", "",
                 f"- Home: {base}/", f"- English blog: {base}/en/blog", "", "## Free tools (no account required)", ""]
        lines += [f"- {t['name']}: {base}/tools/{t['slug']}\n  {t['tagline']}" for t in TOOLS]
        lines += ["", "## Blog", ""] + [f"- {base}/en/blog/{p['slug']}" for p in POSTS]
        return Response("\n".join(lines) + "\n", mimetype="text/plain")

    # ----- errors -----
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error=f"File is larger than {app.config['MAX_UPLOAD_MB']} MB."), 413

    @app.errorhandler(500)
    def server_error(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on our side. Please try again."), 500
        return render_template("404.html", error=True), 500

    return app
