import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))

UPLOADS_DIR = DATA_DIR / "uploads"
VIDEOS_DIR = UPLOADS_DIR / "videos"
IMAGES_DIR = UPLOADS_DIR / "images"
DB_DIR = DATA_DIR / "db"

for path in (VIDEOS_DIR, IMAGES_DIR, DB_DIR):
    path.mkdir(parents=True, exist_ok=True)


def _resolve_base_url() -> str:
    explicit = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    placeholders = {"", "http://localhost:8000", "https://seu-dominio.com"}
    if explicit not in placeholders:
        return explicit

    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        return f"https://{railway_domain}"

    return "http://localhost:8000"


APP_BASE_URL = _resolve_base_url()
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", "500"))
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "20"))

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
