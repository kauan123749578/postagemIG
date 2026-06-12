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
        cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_users)")}
        if cols and "role" not in cols:
            conn.execute("ALTER TABLE admin_users ADD COLUMN role VARCHAR(16) DEFAULT 'admin'")
        if cols and "is_active" not in cols:
            conn.execute("ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        if cols:
            conn.execute("UPDATE admin_users SET role='owner' WHERE id=1 AND role IS NULL")
        conn.commit()
    finally:
        conn.close()
