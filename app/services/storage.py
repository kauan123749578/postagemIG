import os
from pathlib import Path
from urllib.parse import urlparse

from app.config import DATA_DIR, DB_DIR, VIDEOS_DIR
from app.database import DB_PATH, IS_POSTGRES, check_database_connection


def get_storage_status() -> dict:
    data_dir = Path(os.getenv("DATA_DIR", str(DATA_DIR)))
    persistent = str(data_dir).replace("\\", "/") == "/data"
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

    db_connected = check_database_connection()
    db_url = os.getenv("DATABASE_URL", "").strip()
    db_host = ""
    if IS_POSTGRES and db_url:
        parsed = urlparse(db_url.replace("postgresql+psycopg2://", "postgresql://"))
        db_host = parsed.hostname or "postgres"

    if IS_POSTGRES:
        db_ok = db_connected
        warning = None
        if not db_connected:
            warning = "PostgreSQL não conectou. Vincule DATABASE_URL do serviço Postgres ao postagemIG na Railway."
        elif not persistent:
            warning = "Banco OK (Postgres). Vídeos ainda precisam de volume /data no serviço postagemIG."
    else:
        db_ok = DB_PATH.exists() and db_connected
        warning = None
        if not persistent or not writable:
            warning = "Usando SQLite local. Monte volume /data ou configure DATABASE_URL (Postgres) na Railway."

    return {
        "data_dir": str(data_dir),
        "database_type": "postgresql" if IS_POSTGRES else "sqlite",
        "database_host": db_host if IS_POSTGRES else str(DB_PATH),
        "database_connected": db_connected,
        "database_ok": db_ok,
        "persistent_volume": persistent,
        "writable": writable,
        "video_files": video_count,
        "warning": warning,
    }
