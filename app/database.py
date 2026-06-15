import os
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DB_DIR

DB_PATH = DB_DIR / "postagemig.db"


def _normalize_database_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def _build_database_url() -> tuple[str, bool]:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return _normalize_database_url(explicit), True

    return f"sqlite:///{DB_PATH.as_posix()}", False


DATABASE_URL, IS_POSTGRES = _build_database_url()

if IS_POSTGRES:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _table_columns(table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def migrate_schema() -> None:
    if not IS_POSTGRES and not DB_PATH.exists():
        return

    admin_cols = _table_columns("admin_users")
    if admin_cols:
        with engine.begin() as conn:
            if "role" not in admin_cols:
                conn.execute(text("ALTER TABLE admin_users ADD COLUMN role VARCHAR(16) DEFAULT 'admin'"))
            if "is_active" not in admin_cols:
                if IS_POSTGRES:
                    conn.execute(text("ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                else:
                    conn.execute(text("ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            conn.execute(text("UPDATE admin_users SET role='owner' WHERE id=1 AND role IS NULL"))

    account_cols = _table_columns("accounts")
    if account_cols and "fallback_account_id" not in account_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN fallback_account_id INTEGER"))

    loop_cols = _table_columns("loop_configs")
    if loop_cols and "batch_cover_url" not in loop_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE loop_configs ADD COLUMN batch_cover_url TEXT DEFAULT ''"))

    recurring_cols = _table_columns("recurring_batch_configs")
    if recurring_cols and "cover_url" not in recurring_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE recurring_batch_configs ADD COLUMN cover_url TEXT DEFAULT ''"))
    if recurring_cols and "last_attempt_at" not in recurring_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE recurring_batch_configs ADD COLUMN last_attempt_at TIMESTAMP"))
    if recurring_cols and "consecutive_failures" not in recurring_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE recurring_batch_configs ADD COLUMN consecutive_failures INTEGER DEFAULT 0"))

    batch_cols = _table_columns("scheduled_batches")
    if batch_cols and "cover_url" not in batch_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE scheduled_batches ADD COLUMN cover_url TEXT DEFAULT ''"))
