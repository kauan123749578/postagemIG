"""Banco de dados SQLite (SQLAlchemy) e modelos do app desktop."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from core.config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    """WAL + busy_timeout: permite leitura/gravação simultânea (UI + worker)
    sem 'database is locked', evitando que o loop reposte vídeos por falha de commit."""
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
    finally:
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(120), default="")
    password_enc: Mapped[str] = mapped_column(Text, default="")
    sessionid_enc: Mapped[str] = mapped_column(Text, default="")
    session_json: Mapped[str] = mapped_column(Text, default="")
    proxy_url: Mapped[str] = mapped_column(String(512), default="")
    default_caption: Mapped[str] = mapped_column(Text, default="")
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=0)
    max_posts_per_hour: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="unknown")  # healthy/error/pending/unknown
    status_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    logs: Mapped[list["PostLog"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    loop: Mapped["LoopConfig"] = relationship(back_populates="account", cascade="all, delete-orphan", uselist=False)


class PostLog(Base):
    __tablename__ = "post_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    media_id: Mapped[str] = mapped_column(String(64), default="")
    media_type: Mapped[str] = mapped_column(String(20), default="reel")
    caption_preview: Mapped[str] = mapped_column(String(300), default="")
    video_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="success")  # success/error
    error_message: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    account: Mapped["Account"] = relationship(back_populates="logs")


class LoopConfig(Base):
    __tablename__ = "loop_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True, index=True)
    videos_json: Mapped[str] = mapped_column(Text, default="[]")  # lista de {video_path, cover_path, caption}
    interval_seconds: Mapped[int] = mapped_column(Integer, default=120)
    caption: Mapped[str] = mapped_column(Text, default="")
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    # modo: 'continuo' (1 por intervalo) ou 'recorrente' (lote a cada X min)
    mode: Mapped[str] = mapped_column(String(20), default="continuo")
    batch_size: Mapped[int] = mapped_column(Integer, default=3)
    batch_interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    batch_remaining: Mapped[int] = mapped_column(Integer, default=0)

    account: Mapped["Account"] = relationship(back_populates="loop")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    video_path: Mapped[str] = mapped_column(Text, default="")
    cover_path: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/posted/error/cancelled
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info/success/error/warm
    account: Mapped[str] = mapped_column(String(120), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class WarmConfig(Base):
    __tablename__ = "warm_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True, index=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    likes_per_run: Mapped[int] = mapped_column(Integer, default=3)
    stories_per_run: Mapped[int] = mapped_column(Integer, default=3)
    follows_per_run: Mapped[int] = mapped_column(Integer, default=0)
    saves_per_run: Mapped[int] = mapped_column(Integer, default=0)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=45)
    hashtags: Mapped[str] = mapped_column(Text, default="reels,explore,viral,foryou")
    comments_per_run: Mapped[int] = mapped_column(Integer, default=0)
    story_likes_per_run: Mapped[int] = mapped_column(Integer, default=0)
    unfollows_per_run: Mapped[int] = mapped_column(Integer, default=0)
    scrolls_per_run: Mapped[int] = mapped_column(Integer, default=1)
    # janela ativa (hora local 0-23): fora dela o aquecimento pausa sozinho
    active_start_hour: Mapped[int] = mapped_column(Integer, default=8)
    active_end_hour: Mapped[int] = mapped_column(Integer, default=23)
    total_actions: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_summary: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(Text, default="")


class StaggerItem(Base):
    """Fila escalonada: ativa o loop de cada conta em horários espaçados."""
    __tablename__ = "stagger_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    activate_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/activated/cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DailyMetric(Base):
    """Contadores diários por tipo de ação, para os gráficos."""
    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # 'YYYY-MM-DD' (local)
    key: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class Automation(Base):
    """Automação global estilo Instablack: 1 legenda + N vídeos + 1 capa + N contas."""
    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    content_type: Mapped[str] = mapped_column(String(20), default="reel")
    caption: Mapped[str] = mapped_column(Text, default="")
    cover_path: Mapped[str] = mapped_column(Text, default="")
    videos_json: Mapped[str] = mapped_column(Text, default="[]")
    account_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    stagger_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    stagger_min_minutes: Mapped[int] = mapped_column(Integer, default=2)
    stagger_max_minutes: Mapped[int] = mapped_column(Integer, default=8)
    # draft | paused | active | done | error
    status: Mapped[str] = mapped_column(String(20), default="draft")
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    jobs: Mapped[list["AutomationJob"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan"
    )


class AutomationJob(Base):
    """Post individual agendado dentro de uma automação (conta x vídeo)."""
    __tablename__ = "automation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    video_path: Mapped[str] = mapped_column(Text, default="")
    cover_path: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    video_index: Mapped[int] = mapped_column(Integer, default=0)
    account_index: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # pending | posted | error | skipped | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    media_id: Mapped[str] = mapped_column(String(64), default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    automation: Mapped["Automation"] = relationship(back_populates="jobs")


def _ensure_columns() -> None:
    """Migração leve para SQLite: adiciona colunas novas em tabelas já existentes."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    additions = {
        "loop_configs": {
            "mode": "VARCHAR(20) DEFAULT 'continuo'",
            "batch_size": "INTEGER DEFAULT 3",
            "batch_interval_minutes": "INTEGER DEFAULT 360",
            "batch_remaining": "INTEGER DEFAULT 0",
        },
        "warm_configs": {
            "comments_per_run": "INTEGER DEFAULT 0",
            "story_likes_per_run": "INTEGER DEFAULT 0",
            "unfollows_per_run": "INTEGER DEFAULT 0",
            "scrolls_per_run": "INTEGER DEFAULT 1",
            "active_start_hour": "INTEGER DEFAULT 8",
            "active_end_hour": "INTEGER DEFAULT 23",
        },
        "accounts": {
            "sessionid_enc": "TEXT DEFAULT ''",
        },
    }
    with engine.begin() as conn:
        for table, cols in additions.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
