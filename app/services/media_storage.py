import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import (
    APP_BASE_URL,
    IMAGE_EXTENSIONS,
    IMAGES_DIR,
    MAX_IMAGE_MB,
    MAX_VIDEO_MB,
    VIDEO_EXTENSIONS,
    VIDEOS_DIR,
)


def _public_url(kind: str, filename: str) -> str:
    return f"{APP_BASE_URL}/media/{kind}/{filename}"


def _save_file(file: UploadFile, dest_dir: Path, allowed: set[str], max_mb: int, kind: str) -> dict:
    if not file.filename:
        raise HTTPException(400, "Arquivo sem nome")

    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Formato não permitido: {ext}")

    content = file.file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > max_mb:
        raise HTTPException(400, f"Arquivo muito grande ({size_mb:.1f}MB). Máximo: {max_mb}MB")

    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = dest_dir / safe_name
    path.write_bytes(content)

    return {
        "filename": safe_name,
        "original_name": file.filename,
        "url": _public_url(kind, safe_name),
        "kind": kind,
        "size_mb": round(size_mb, 2),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def save_video(file: UploadFile) -> dict:
    return _save_file(file, VIDEOS_DIR, VIDEO_EXTENSIONS, MAX_VIDEO_MB, "videos")


def save_image(file: UploadFile) -> dict:
    return _save_file(file, IMAGES_DIR, IMAGE_EXTENSIONS, MAX_IMAGE_MB, "images")


def list_media() -> dict:
    videos = _list_dir(VIDEOS_DIR, "videos")
    images = _list_dir(IMAGES_DIR, "images")
    return {"videos": videos, "images": images, "base_url": APP_BASE_URL}


def _list_dir(directory: Path, kind: str) -> list[dict]:
    if not directory.exists():
        return []
    items = []
    for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append({
            "filename": path.name,
            "original_name": path.name,
            "url": _public_url(kind, path.name),
            "kind": kind,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return items
