from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(120), default="")
    ig_user_id: Mapped[str] = mapped_column(String(64))
    access_token: Mapped[str] = mapped_column(Text)
    proxy_url: Mapped[str] = mapped_column(String(512), default="")
    graph_api_version: Mapped[str] = mapped_column(String(16), default="v21.0")
    graph_host: Mapped[str] = mapped_column(String(64), default="graph.facebook.com")

    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=100)
    max_posts_per_hour: Mapped[int] = mapped_column(Integer, default=25)
    default_caption: Mapped[str] = mapped_column(Text, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    health_message: Mapped[str] = mapped_column(Text, default="")
    profile_views: Mapped[int] = mapped_column(Integer, default=0)
    total_reach: Mapped[int] = mapped_column(Integer, default=0)
    total_impressions: Mapped[int] = mapped_column(Integer, default=0)

    fallback_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    post_logs: Mapped[list["PostLog"]] = relationship(back_populates="account")
    loop_config: Mapped["LoopConfig | None"] = relationship(
        back_populates="account", uselist=False
    )


class PostLog(Base):
    __tablename__ = "post_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    media_id: Mapped[str] = mapped_column(String(64), default="")
    media_type: Mapped[str] = mapped_column(String(32))
    caption_preview: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(32))
    error_message: Mapped[str] = mapped_column(Text, default="")
    views: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped["Account"] = relationship(back_populates="post_logs")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LoopConfig(Base):
    __tablename__ = "loop_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True)
    videos_json: Mapped[str] = mapped_column(Text, default="[]")
    caption: Mapped[str] = mapped_column(Text, default="")
    batch_size: Mapped[int] = mapped_column(Integer, default=4)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    batches_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    account: Mapped["Account"] = relationship(back_populates="loop_config")


class ScheduledBatch(Base):
    __tablename__ = "scheduled_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    fallback_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    items: Mapped[list["ScheduledPost"]] = relationship(back_populates="batch")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_batches.id"), nullable=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    fallback_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)

    video_url: Mapped[str] = mapped_column(Text)
    cover_url: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    media_type: Mapped[str] = mapped_column(String(32), default="reel")

    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str] = mapped_column(Text, default="")
    media_id: Mapped[str] = mapped_column(String(64), default="")
    posted_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch: Mapped["ScheduledBatch | None"] = relationship(back_populates="items")
