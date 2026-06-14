import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import Account, ScheduledPost
from app.services.instagram import InstagramAPIError
from app.services.publisher import publish_reel

logger = logging.getLogger("schedule_worker")
_worker_task: asyncio.Task | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _process_due_posts() -> None:
    db = SessionLocal()
    try:
        now = _utcnow()
        due = (
            db.query(ScheduledPost)
            .options(joinedload(ScheduledPost.batch))
            .filter(ScheduledPost.status == "pending")
            .order_by(ScheduledPost.scheduled_at, ScheduledPost.sort_order)
            .limit(20)
            .all()
        )

        for item in due:
            if _normalize_dt(item.scheduled_at) > now:
                continue

            item.status = "processing"
            db.commit()

            account = db.get(Account, item.account_id)
            if not account:
                item.status = "error"
                item.error_message = "Conta não encontrada"
                db.commit()
                continue

            if item.fallback_account_id:
                account.fallback_account_id = item.fallback_account_id

            try:
                result = publish_reel(
                    db,
                    account,
                    item.video_url,
                    caption=item.caption,
                    cover_url=item.cover_url or None,
                )
                item.status = "posted"
                item.media_id = result["media_id"]
                item.posted_account_id = result["account_id"]
                item.posted_at = _utcnow()
                item.error_message = "Contingência usada" if result.get("used_fallback") else ""
                db.commit()
                logger.info("Agendamento %s publicado: %s", item.id, result["media_id"])
            except InstagramAPIError as exc:
                item.status = "error"
                item.error_message = str(exc)
                db.commit()
                logger.error("Agendamento %s falhou: %s", item.id, exc)
    except Exception:
        logger.exception("Erro no schedule worker")
        db.rollback()
    finally:
        db.close()


async def _worker_loop() -> None:
    while True:
        await asyncio.to_thread(_process_due_posts)
        await asyncio.sleep(15)


def start_schedule_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Schedule worker iniciado")
