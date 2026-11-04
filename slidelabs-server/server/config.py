import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if value.strip():
            os.environ.setdefault(key.strip(), value.strip())


def _secret_key(instance: Path) -> str:
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    instance.mkdir(parents=True, exist_ok=True)
    f = instance / "secret_key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


def load_config(overrides=None) -> dict:
    _load_dotenv(ROOT / ".env")
    instance = ROOT / "instance"
    cfg = {
        "ROOT": ROOT,
        "PORT": int(os.environ.get("PORT", 5000)),
        "SECRET_KEY": _secret_key(instance),
        "DOWNLOAD_DIR": str(ROOT / os.environ.get("DOWNLOAD_DIR", "instance/files")),
        "FILE_TTL_SECONDS": int(os.environ.get("FILE_TTL_SECONDS", 3600)),
        "MAX_DOWNLOAD_MB": int(os.environ.get("MAX_DOWNLOAD_MB", 500)),
        "MAX_UPLOAD_MB": int(os.environ.get("MAX_UPLOAD_MB", 50)),
        "IMAGE_PAGE_HOSTS": [h.strip().lower() for h in os.environ.get("IMAGE_PAGE_HOSTS", "tiktok.com").split(",") if h.strip()],
        "ALLOW_PRIVATE_URLS": os.environ.get("ALLOW_PRIVATE_URLS", "0") == "1",
        "SITE_URL": os.environ.get("SITE_URL", "http://127.0.0.1:5000"),
    }
    if overrides:
        cfg.update(overrides)
    cfg["MAX_CONTENT_LENGTH"] = cfg["MAX_UPLOAD_MB"] * 1024 * 1024
    return cfg
