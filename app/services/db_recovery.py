import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.config import DB_DIR
from app.database import DB_PATH, IS_POSTGRES, engine
from app.models import Account

logger = logging.getLogger("db_recovery")

LAST_RECOVERY: dict = {"recovered": False}

_RECOVERY_TABLES = (
    "accounts",
    "app_settings",
    "loop_configs",
    "recurring_batch_configs",
    "scheduled_batches",
    "scheduled_posts",
    "post_logs",
)


def _sqlite_path() -> Path:
    return Path(DB_PATH)


def sqlite_backup_info() -> dict:
    path = _sqlite_path()
    if not path.exists():
        return {"exists": False, "path": str(path), "accounts": 0, "size_kb": 0}

    sqlite_engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    try:
        with sqlite_engine.connect() as conn:
            tables = inspect(sqlite_engine).get_table_names()
            accounts = 0
            if "accounts" in tables:
                accounts = conn.execute(text("SELECT COUNT(*) FROM accounts")).scalar() or 0
    except Exception as exc:
        return {"exists": True, "path": str(path), "accounts": 0, "error": str(exc)}
    finally:
        sqlite_engine.dispose()

    return {
        "exists": True,
        "path": str(path),
        "accounts": accounts,
        "size_kb": round(path.stat().st_size / 1024, 1),
    }


def _copy_table(src_conn, dst_conn, table: str, pg_columns: set[str]) -> int:
    rows = src_conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
    if not rows:
        return 0

    common = [col for col in rows[0].keys() if col in pg_columns]
    if not common:
        return 0

    col_list = ", ".join(common)
    placeholders = ", ".join(f":{c}" for c in common)
    for row in rows:
        payload = {c: row[c] for c in common}
        dst_conn.execute(
            text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"),
            payload,
        )
    return len(rows)


def _reset_id_sequence(dst_conn, table: str) -> None:
    try:
        dst_conn.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1)
                )
                """
            )
        )
    except Exception:
        pass


def recover_sqlite_to_postgres(db: Session) -> dict:
    global LAST_RECOVERY

    if not IS_POSTGRES:
        result = {"recovered": False, "reason": "not_postgres"}
        LAST_RECOVERY = result
        return result

    sqlite_path = _sqlite_path()
    if not sqlite_path.exists():
        result = {"recovered": False, "reason": "no_sqlite_file"}
        LAST_RECOVERY = result
        return result

    if db.query(Account).count() > 0:
        result = {"recovered": False, "reason": "postgres_not_empty"}
        LAST_RECOVERY = result
        return result

    backup = sqlite_backup_info()
    if backup.get("accounts", 0) == 0:
        result = {"recovered": False, "reason": "sqlite_empty"}
        LAST_RECOVERY = result
        return result

    sqlite_engine = create_engine(
        f"sqlite:///{sqlite_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    copied: dict[str, int] = {}
    pg_inspector = inspect(engine)

    try:
        with sqlite_engine.connect() as src, engine.begin() as dst:
            sqlite_tables = set(inspect(sqlite_engine).get_table_names())
            for table in _RECOVERY_TABLES:
                if table not in sqlite_tables:
                    continue
                pg_cols = {c["name"] for c in pg_inspector.get_columns(table)}
                count = _copy_table(src, dst, table, pg_cols)
                if count:
                    copied[table] = count
                    if "id" in pg_cols:
                        _reset_id_sequence(dst, table)
    except Exception as exc:
        logger.exception("Falha ao recuperar SQLite → Postgres")
        result = {"recovered": False, "reason": "error", "error": str(exc)}
        LAST_RECOVERY = result
        return result
    finally:
        sqlite_engine.dispose()

    archive = None
    try:
        archive = sqlite_path.with_suffix(
            f".recovered-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.db"
        )
        shutil.move(str(sqlite_path), str(archive))
    except OSError:
        archive = None

    total = sum(copied.values())
    logger.info("Recuperação SQLite → Postgres: %s registros — %s", total, copied)
    result = {
        "recovered": True,
        "tables": copied,
        "total_rows": total,
        "archived_sqlite": str(archive) if archive else None,
    }
    LAST_RECOVERY = result
    return result
