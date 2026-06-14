import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import LoopConfig
from app.services.instagram import InstagramAPIError
from app.services.publisher import publish_reel
from app.services.rate_limit import can_post

logger = logging.getLogger("loop_worker")
_worker_task: asyncio.Task | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_videos(videos_json: str) -> list[dict]:
    try:
        data = json.loads(videos_json or "[]")
        if isinstance(data, list):
            return [v for v in data if isinstance(v, dict) and v.get("video_url")]
    except json.JSONDecodeError:
        pass
    return []


def _caption_for_loop(loop: LoopConfig, account) -> str:
    if loop.caption.strip():
        return loop.caption.strip()
    return account.default_caption.strip()


def _process_single_loop(loop_id: int) -> None:
    db = SessionLocal()
    try:
        loop = (
            db.query(LoopConfig)
            .options(joinedload(LoopConfig.account))
            .filter(LoopConfig.id == loop_id)
            .first()
        )
        if not loop or not loop.is_running:
            return

        account = loop.account
        if not account or not account.is_active:
            loop.last_error = "Conta inativa ou não encontrada"
            return

        videos = _parse_videos(loop.videos_json)
        if not videos:
            loop.last_error = "Nenhum vídeo configurado no loop"
            return

        allowed, reason = can_post(
            db, account.id, account.max_posts_per_day, account.max_posts_per_hour
        )
        if not allowed:
            loop.last_error = f"Aguardando limite: {reason}"
            return

        if loop.last_post_at and loop.interval_seconds > 0:
            last = loop.last_post_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (_utcnow() - last).total_seconds()
            if elapsed < loop.interval_seconds:
                return

        index = loop.current_index % len(videos)
        item = videos[index]
        video_url = item["video_url"]
        cover_url = item.get("cover_url") or None
        caption = _caption_for_loop(loop, account)

        try:
            result = publish_reel(db, account, video_url, caption, cover_url=cover_url)
            media_id = result["media_id"]
            used = result.get("used_fallback")
            loop.last_error = "Contingência usada" if used else ""
            loop.total_posts += 1
            loop.last_post_at = _utcnow()
            loop.current_index = (index + 1) % len(videos)

            if loop.current_index % loop.batch_size == 0:
                loop.batches_completed += 1

            logger.info(
                "Loop conta %s: post %s (lote %s, índice %s%s)",
                account.name,
                media_id,
                loop.batches_completed,
                index,
                ", contingência" if used else "",
            )
        except InstagramAPIError as exc:
            loop.last_error = str(exc)

        db.commit()
    except Exception as exc:
        logger.exception("Erro no loop %s: %s", loop_id, exc)
        db.rollback()
    finally:
        db.close()


async def _worker_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            running = db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).all()
            loop_ids = [loop.id for loop in running]
        finally:
            db.close()

        for loop_id in loop_ids:
            await asyncio.to_thread(_process_single_loop, loop_id)

        await asyncio.sleep(5)


def start_loop_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Loop worker iniciado (contínuo, sem pausa entre lotes)")
