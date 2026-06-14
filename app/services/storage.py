import os
from pathlib import Path

from app.config import DATA_DIR, DB_DIR, VIDEOS_DIR


def get_storage_status() -> dict:
    data_dir = Path(os.getenv("DATA_DIR", str(DATA_DIR)))
    persistent = str(data_dir).replace("\\", "/") == "/data"
    db_exists = (DB_DIR / "postagemig.db").exists()
    video_count = len(list(VIDEOS_DIR.glob("*"))) if VIDEOS_DIR.exists() else 0

    writable = False
    probe = data_dir / ".write_probe"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError:
        writable = False

    return {
        "data_dir": str(data_dir),
        "persistent_volume": persistent,
        "writable": writable,
        "database_exists": db_exists,
        "video_files": video_count,
        "warning": None if persistent and writable else (
            "Dados podem ser perdidos no redeploy. Monte um volume em /data na Railway."
        ),
    }
