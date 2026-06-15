from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PostLog


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def count_posts_since(db: Session, account_id: int, since: datetime) -> int:
    stmt = (
        select(func.count(PostLog.id))
        .where(PostLog.account_id == account_id)
        .where(PostLog.status == "success")
        .where(PostLog.posted_at >= since)
    )
    return db.scalar(stmt) or 0


def can_post(db: Session, account_id: int, max_per_day: int, max_per_hour: int) -> tuple[bool, str]:
    now = _utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    posts_hour = count_posts_since(db, account_id, hour_ago)
    posts_day = count_posts_since(db, account_id, day_ago)

    if max_per_day > 0 and posts_day >= max_per_day:
        return False, f"Limite diário atingido ({posts_day}/{max_per_day})"
    if max_per_hour > 0 and posts_hour >= max_per_hour:
        return False, f"Limite por hora atingido ({posts_hour}/{max_per_hour})"
    return True, ""


def usage_stats(db: Session, account_id: int, max_per_day: int, max_per_hour: int) -> dict:
    now = _utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)
    posts_hour = count_posts_since(db, account_id, hour_ago)
    posts_day = count_posts_since(db, account_id, day_ago)
    unlimited_day = max_per_day <= 0
    unlimited_hour = max_per_hour <= 0
    return {
        "posts_last_hour": posts_hour,
        "posts_last_24h": posts_day,
        "max_per_hour": max_per_hour,
        "max_per_day": max_per_day,
        "unlimited_hour": unlimited_hour,
        "unlimited_day": unlimited_day,
        "remaining_hour": None if unlimited_hour else max(0, max_per_hour - posts_hour),
        "remaining_day": None if unlimited_day else max(0, max_per_day - posts_day),
    }
