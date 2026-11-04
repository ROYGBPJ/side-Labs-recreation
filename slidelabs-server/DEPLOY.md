# Free hosting (server version, with video + PDF support)

"Free .com" doesn't exist: .com names cost about $10/year. Free hosts give a free subdomain
(e.g. yourname.onrender.com or yourname-slidelabs.hf.space). Connect a purchased .com later in the host's settings.

## Option A: Render (free web service)
1. Put this folder in a GitHub repo.
2. render.com -> New -> Web Service -> pick the repo. It detects the Dockerfile. Choose the Free plan.
3. Add env var SITE_URL = the https URL Render gives you. Deploy.
Free instances sleep after ~15 min idle (first visit is slow) and downloaded files are temporary.

## Option B: Hugging Face Spaces (free, no sleep on CPU basic)
1. huggingface.co -> New Space -> SDK: Docker.
2. Upload this folder's files (README.md needs the header below at the very top).
3. It builds from the Dockerfile and serves on port 7860.
   README header:  ---\ntitle: SlideLabs\nsdk: docker\napp_port: 7860\n---

## Not recommended
PythonAnywhere free blocks most outside sites, so the downloader would fail.

## Caveats
- YouTube/TikTok often block data-centre IPs, so video downloads from those sites may fail on any free host.
- Free tiers are shared and small: large videos may time out.
- Add your own .com: buy it at any registrar, then add it as a custom domain in Render/Spaces and set the DNS records they show.
