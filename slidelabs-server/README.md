# SlideLabs recreation (English only, no pricing, no login)

An independent, runnable reimplementation of the public SlideLabs site (slidelabs.net), built from the supplied
`sitemap.xml`, `robots.txt` and `llms.txt`. It is **not** the original source code.

## Install and run

Requires Python 3.11+ and `ffmpeg` on PATH (needed for HD merge and MP3 extraction).

```bash
pip install -r requirements.txt
cp .env.example .env        # optional
python run.py               # http://127.0.0.1:5000
```

Tests:

```bash
python -m pytest -q tests                 # 50 API/page/link tests
python tests/e2e_browser.py               # Playwright + Chrome: layouts, menus, tool flows
# first time only: playwright install chromium  (the script uses /usr/bin/google-chrome; edit the path if different)
```

Configuration (`.env.example`): `PORT`, `SECRET_KEY`, `DOWNLOAD_DIR`, `FILE_TTL_SECONDS`, `MAX_DOWNLOAD_MB`,
`MAX_UPLOAD_MB`, `IMAGE_PAGE_HOSTS`, `SITE_URL`, `ALLOW_PRIVATE_URLS` (keep 0 in production).

## Scope decisions (from you)
- English pages only (`/en/blog/...`; the Vietnamese `/blog/...` pages are not built).
- No pricing page. No login/account/dashboard.

## Original pages and recreation checklist

Source: your sitemap (35 URLs) plus `llms.txt`.

| Original URL | Status |
|---|---|
| `/` | Recreated |
| `/how-it-works` | Recreated |
| `/tools/video-downloader` | Recreated, working backend |
| `/tools/tiktok-image-downloader` | Recreated, working backend |
| `/tools/notebooklm-watermark-remover` | Recreated, working backend |
| `/en/blog` + 11 articles (`kol-la-gi`, `koc-la-gi`, `kol-koc-influencer-khac-nhau`, `ugc-la-gi`, `danh-sach-kol-theo-linh-vuc`, `top-kol-tiktok`, `thue-kol-quang-cao-san-pham`, `booking-kol-koc-gia-bao-nhieu`, `platform-tim-kiem-kol-koc`, `cong-cu-tim-influencer`, `cach-tim-koc-tiktok`) | Recreated (12 pages) |
| `/sitemap.xml`, `/robots.txt`, `/llms.txt` | Recreated (generated, English-only) |
| `/pricing` | Omitted by request |
| `/login`, `/dashboard/` | Omitted by request |
| `/blog` + 15 Vietnamese articles | Omitted by request (English only) |

17 pages + 3 crawler files are served.

## Features
Responsive header (dropdown, mobile menu), footer, home, how-it-works, three working tools, blog index and
11 articles with Article JSON-LD, 404/500 pages, per-page titles/descriptions/canonical tags, loading/error/success
states on every tool, skip link and focus styles, reduced-motion support.

## Backend functionality (reimplemented, not recovered)
- **Video downloader** (`server/downloader.py`): `POST /api/video/info`, `POST /api/video/download` using yt-dlp.
  Requires a rights confirmation. DRM formats are never requested; no cookies or credentials are accepted.
- **TikTok Shop image extractor** (`server/images.py`): `POST /api/images/extract`, `GET /api/images/fetch`,
  `POST /api/images/zip`. Page hosts restricted to `IMAGE_PAGE_HOSTS` (default `tiktok.com`); images are fetched
  only through signed tokens, so it is not an open proxy.
- **Watermark remover** (`server/watermark.py`): `POST /api/watermark` for PPTX (python-pptx) and PDF (PyMuPDF).
- Shared: SSRF guard (public addresses only, redirects re-checked), temp-file store with expiry (`/api/files/<id>`).

## Test results (run in this environment)
- `pytest`: 50 passed (every page loads, every internal link/asset resolves, sitemap matches pages, no pricing or
  login references, video info/download/MP3 against a local file, image extract/zip/forged-token rejection,
  PPTX and PDF watermark removal and "nothing found" path, validation and error paths, SSRF blocking).
- Browser (`tests/e2e_browser.py`): no horizontal overflow and no console/network errors on all 17 pages at 375,
  768 and 1280 px; menus open; video, image (thumbnails + ZIP) and watermark flows work end to end.

## Limitations and unverified items
- **Unverified against the original:** the live site was unreachable from this environment, so layout, colours,
  copy and header/footer structure are inferred from `llms.txt`, the page metadata and the `#4f46e5` theme color.
  No pixel comparison was possible. Fonts: system stack. Logo is an original placeholder mark, not the real one.
- **Blog articles** are newly written original text matching the sitemap slugs and topics; the original wording was
  never seen. Dates use the sitemap `lastmod` (2026-05-17).
- **Video downloader:** tested against a local MP4 only. Real-site support (TikTok, YouTube, etc.) depends on
  yt-dlp and those sites at run time and was not tested; sites may block server IPs.
- **TikTok image extractor:** extraction heuristics (og:image, `<img>`, image URLs in embedded JSON) are inferred and
  were tested only on a local page, not on real TikTok Shop pages.
- **Watermark remover:** built without a real NotebookLM export. It removes "NotebookLM" text and repeated
  bottom-right pictures. A watermark baked into full-slide images is not removable and is reported as "not found".
  PDF removal fills with a sampled background colour, which may show on patterned backgrounds.
- The original AI workspace (Visual Studio, Campaign Kit, KOL Matching, etc.) is marketed on the site but sits
  behind login; it is not recreated. The home and how-it-works pages describe it only.
- DNS-rebinding between the SSRF check and the fetch is not fully mitigated.
