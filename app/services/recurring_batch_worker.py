import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Account, RecurringBatchConfig
from app.services.instagram import InstagramAPIError
from app.services.publisher import publish_reel
from app.services.rate_limit import can_post

logger = logging.getLogger("recurring_batch_worker")
_worker_task: asyncio.Task | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_videos(videos_json: str) -> list[dict]:
    try:
        data = json.loads(videos_json or "[]")
        if isinstance(data, list):
            return [v for v in data if isinstance(v, dict) and v.get("video_url")]
    except json.JSONDecodeError:
        pass
    return []


def _process_recurring_batch(config_id: int) -> None:
    db = SessionLocal()
    try:
        config = (
            db.query(RecurringBatchConfig)
            .filter(RecurringBatchConfig.id == config_id)
            .first()
        )
        if not config or not config.is_running:
            return

        now = _utcnow()
        ends_at = _normalize_dt(config.ends_at)
        if ends_at and now >= ends_at:
            config.is_running = False
            config.last_error = f"Duração concluída ({config.duration_hours}h)"
            db.commit()
            logger.info("Lote recorrente conta %s encerrado por tempo", config.account_id)
            return

        account = db.get(Account, config.account_id)
        if not account or not account.is_active:
            config.last_error = "Conta inativa"
            return

        videos = _parse_videos(config.videos_json)
        if not videos:
            config.last_error = "Nenhum vídeo no lote"
            return

        if config.cycle_video_index == 0 and config.last_cycle_at:
            last_cycle = _normalize_dt(config.last_cycle_at)
            wait_seconds = config.cycle_interval_hours * 3600
            if last_cycle and (now - last_cycle).total_seconds() < wait_seconds:
                return

        last_post = _normalize_dt(config.last_post_at)
        if last_post and config.video_interval_seconds > 0:
            if (now - last_post).total_seconds() < config.video_interval_seconds:
                return

        allowed, reason = can_post(
            db, account.id, account.max_posts_per_day, account.max_posts_per_hour
        )
        if not allowed:
            config.last_error = f"Aguardando limite: {reason}"
            db.commit()
            return

        index = config.cycle_video_index % len(videos)
        item = videos[index]
        caption = config.caption or account.default_caption or ""
        cover_url = item.get("cover_url") or config.cover_url or None

        try:
            result = publish_reel(
                db,
                account,
                item["video_url"],
                caption,
                cover_url=cover_url,
            )
            config.total_posts += 1
            config.last_post_at = now
            config.last_error = "Contingência usada" if result.get("used_fallback") else ""
            config.cycle_video_index = index + 1

            if config.cycle_video_index >= len(videos):
                config.cycle_video_index = 0
                config.cycles_completed += 1
                config.last_cycle_at = now
                logger.info(
                    "Lote recorrente conta %s: ciclo %s concluído",
                    account.name,
                    config.cycles_completed,
                )

            db.commit()
        except InstagramAPIError as exc:
            config.last_error = str(exc)
            db.commit()
    except Exception:
        logger.exception("Erro no lote recorrente %s", config_id)
        db.rollback()
    finally:
        db.close()


async def _worker_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            running = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.is_running.is_(True)).all()
            config_ids = [c.id for c in running]
        finally:
            db.close()

        for config_id in config_ids:
            await asyncio.to_thread(_process_recurring_batch, config_id)

        await asyncio.sleep(5)


def start_recurring_batch_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Recurring batch worker iniciado")
