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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from core.config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})
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


def init_db() -> None:
    Base.metadata.create_all(engine)
