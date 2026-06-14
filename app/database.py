from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DB_DIR

DB_PATH = DB_DIR / "postagemig.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
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


def migrate_schema() -> None:
    import sqlite3

    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        admin_cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_users)")}
        if admin_cols and "role" not in admin_cols:
            conn.execute("ALTER TABLE admin_users ADD COLUMN role VARCHAR(16) DEFAULT 'admin'")
        if admin_cols and "is_active" not in admin_cols:
            conn.execute("ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        if admin_cols:
            conn.execute("UPDATE admin_users SET role='owner' WHERE id=1 AND role IS NULL")

        account_cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        if account_cols and "fallback_account_id" not in account_cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN fallback_account_id INTEGER")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                account_id INTEGER NOT NULL,
                fallback_account_id INTEGER,
                created_at DATETIME
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                account_id INTEGER NOT NULL,
                fallback_account_id INTEGER,
                video_url TEXT NOT NULL,
                cover_url TEXT DEFAULT '',
                caption TEXT DEFAULT '',
                media_type VARCHAR(32) DEFAULT 'reel',
                scheduled_at DATETIME NOT NULL,
                status VARCHAR(32) DEFAULT 'pending',
                error_message TEXT DEFAULT '',
                media_id VARCHAR(64) DEFAULT '',
                posted_account_id INTEGER,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME,
                posted_at DATETIME
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recurring_batch_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL UNIQUE,
                name VARCHAR(120) DEFAULT 'Lote recorrente',
                videos_json TEXT DEFAULT '[]',
                caption TEXT DEFAULT '',
                fallback_account_id INTEGER,
                duration_hours INTEGER DEFAULT 12,
                cycle_interval_hours INTEGER DEFAULT 1,
                video_interval_seconds INTEGER DEFAULT 60,
                is_running BOOLEAN DEFAULT 0,
                started_at DATETIME,
                ends_at DATETIME,
                cycle_video_index INTEGER DEFAULT 0,
                cycles_completed INTEGER DEFAULT 0,
                total_posts INTEGER DEFAULT 0,
                last_post_at DATETIME,
                last_cycle_at DATETIME,
                last_error TEXT DEFAULT ''
            )
        """)
        conn.commit()
    finally:
        conn.close()
