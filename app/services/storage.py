import os
from pathlib import Path
from urllib.parse import urlparse

from app.config import DATA_DIR, DB_DIR, VIDEOS_DIR
from app.database import DB_PATH, IS_POSTGRES, check_database_connection
from app.services.db_recovery import LAST_RECOVERY, sqlite_backup_info


def get_storage_status(db=None) -> dict:
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

    sqlite_info = sqlite_backup_info()
    accounts_count = 0
    post_logs_count = 0
    if db is not None:
        try:
            from app.models import Account, PostLog

            accounts_count = db.query(Account).count()
            post_logs_count = db.query(PostLog).count()
        except Exception:
            pass

    warning = None
    if IS_POSTGRES:
        db_ok = db_connected
        if not db_connected:
            warning = "PostgreSQL não conectou. Vincule DATABASE_URL do serviço Postgres ao postagemIG na Railway."
        elif accounts_count == 0 and sqlite_info.get("accounts", 0) > 0:
            warning = (
                f"Postgres vazio mas backup SQLite encontrado ({sqlite_info['accounts']} contas em "
                f"{sqlite_info['path']}). Reinicie o serviço para recuperar automaticamente."
            )
        elif accounts_count == 0 and sqlite_info.get("exists") and sqlite_info.get("accounts", 0) == 0:
            warning = "Banco Postgres conectado mas sem contas. Os dados podem ter sido perdidos se o volume Postgres foi recriado na Railway."
        elif not persistent:
            warning = "Banco OK (Postgres). Vídeos ainda precisam de volume /data no serviço postagemIG."
    else:
        db_ok = DB_PATH.exists() and db_connected
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
        "accounts_count": accounts_count,
        "post_logs_count": post_logs_count,
        "sqlite_backup": sqlite_info,
        "recovery": LAST_RECOVERY,
        "warning": warning,
    }
