"""Caminhos e constantes do app desktop.

Tudo fica numa pasta `data/` ao lado do programa (portátil).
Quando empacotado com PyInstaller, usa a pasta do executável.
"""
import sys
from pathlib import Path

APP_NAME = "Postagem IG"
APP_VERSION = "1.0.0"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):  # rodando como .exe (PyInstaller)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
VIDEOS_DIR = DATA_DIR / "uploads" / "videos"
IMAGES_DIR = DATA_DIR / "uploads" / "images"
DB_PATH = DATA_DIR / "app.db"
KEY_PATH = DATA_DIR / "secret.key"
LOCAL_FFMPEG = BASE_DIR / "ffmpeg.exe"

for _p in (DATA_DIR, SESSIONS_DIR, VIDEOS_DIR, IMAGES_DIR):
    _p.mkdir(parents=True, exist_ok=True)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

INSTAGRAM_CAPTION_MAX = 2200
