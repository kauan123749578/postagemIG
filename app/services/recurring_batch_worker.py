import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Account, RecurringBatchConfig
from app.services.instagram import InstagramAPIError
from app.services.publisher import publish_reel, resolve_post_accounts
from app.services.rate_limit import can_post

logger = logging.getLogger("recurring_batch_worker")
_worker_task: asyncio.Task | None = None
_config_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()

MAX_VIDEO_FAILURES = 3
FAILURE_BACKOFF_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _config_lock(config_id: int) -> threading.Lock:
    with _locks_guard:
        if config_id not in _config_locks:
            _config_locks[config_id] = threading.Lock()
        return _config_locks[config_id]


def _parse_videos(videos_json: str) -> list[dict]:
    try:
        data = json.loads(videos_json or "[]")
        if isinstance(data, list):
            seen: set[str] = set()
            unique: list[dict] = []
            for v in data:
                if not isinstance(v, dict):
                    continue
                url = (v.get("video_url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                cover = (v.get("cover_url") or "").strip()
                unique.append({**v, "video_url": url, "cover_url": cover})
            return unique
    except json.JSONDecodeError:
        pass
    return []


def _wait_seconds(config: RecurringBatchConfig, now: datetime) -> int | None:
    """Retorna segundos restantes de espera, ou None se pode postar."""
    is_retry = (config.consecutive_failures or 0) > 0
    if config.cycle_video_index == 0 and not is_retry:
        return None

    last_event = _normalize_dt(config.last_attempt_at) or _normalize_dt(config.last_post_at)
    if not last_event:
        return None

    base_wait = config.video_interval_seconds or 0
    if is_retry:
        base_wait = max(base_wait, FAILURE_BACKOFF_SECONDS)

    if base_wait <= 0:
        return None

    elapsed = (now - last_event).total_seconds()
    remaining = base_wait - elapsed
    return int(remaining) if remaining > 0 else None


def _advance_after_success(config: RecurringBatchConfig, videos_count: int, now: datetime) -> None:
    config.cycle_video_index += 1
    config.total_posts += 1
    config.last_post_at = now
    config.last_attempt_at = now
    config.consecutive_failures = 0
    config.last_error = ""

    if config.cycle_video_index >= videos_count:
        config.cycle_video_index = 0
        config.cycles_completed += 1
        config.last_cycle_at = now


def _advance_after_skip(config: RecurringBatchConfig, videos_count: int, now: datetime, reason: str) -> None:
    skipped = config.cycle_video_index + 1
    config.cycle_video_index += 1
    config.consecutive_failures = 0
    config.last_attempt_at = now
    config.last_error = reason

    if config.cycle_video_index >= videos_count:
        config.cycle_video_index = 0
        config.cycles_completed += 1
        config.last_cycle_at = now

    logger.warning(
        "Lote recorrente conta %s: vídeo %s/%s pulado — %s",
        config.account_id,
        skipped,
        videos_count,
        reason,
    )


def _process_recurring_batch(config_id: int) -> None:
    lock = _config_lock(config_id)
    if not lock.acquire(blocking=False):
        return

    db = SessionLocal()
    try:
        config = (
            db.query(RecurringBatchConfig)
            .filter(RecurringBatchConfig.id == config_id)
            .with_for_update()
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
        if not account:
            config.last_error = "Conta não encontrada"
            db.commit()
            return

        post_account, _ = resolve_post_accounts(db, account)
        if not post_account or not post_account.is_active:
            config.last_error = "Conta inativa e sem contingência disponível"
            db.commit()
            return

        videos = _parse_videos(config.videos_json)
        if not videos:
            config.last_error = "Nenhum vídeo no lote"
            db.commit()
            return

        if config.cycle_video_index >= len(videos):
            config.cycle_video_index = 0

        if config.cycle_video_index == 0 and config.last_cycle_at:
            last_cycle = _normalize_dt(config.last_cycle_at)
            wait_seconds = config.cycle_interval_hours * 3600
            if last_cycle and (now - last_cycle).total_seconds() < wait_seconds:
                return

        wait_left = _wait_seconds(config, now)
        if wait_left:
            return

        allowed, reason = can_post(
            db, post_account.id, post_account.max_posts_per_day, post_account.max_posts_per_hour
        )
        if not allowed:
            config.last_error = f"Aguardando limite: {reason}"
            db.commit()
            return

        index = config.cycle_video_index
        item = videos[index]
        caption = config.caption or account.default_caption or ""
        item_cover = item.get("cover_url") or ""
        batch_cover = config.cover_url or ""

        config.last_attempt_at = now
        db.commit()

        try:
            result = publish_reel(
                db,
                account,
                item["video_url"],
                caption,
                cover_url=item_cover,
                batch_cover_url=batch_cover,
                video_index=index + 1,
            )
            config = (
                db.query(RecurringBatchConfig)
                .filter(RecurringBatchConfig.id == config_id)
                .with_for_update()
                .first()
            )
            if not config:
                return

            _advance_after_success(config, len(videos), now)
            if result.get("used_fallback"):
                config.last_error = "Contingência usada"
            db.commit()
            logger.info(
                "Lote recorrente conta %s: vídeo %s/%s publicado (ciclo %s)",
                account.name,
                index + 1,
                len(videos),
                config.cycles_completed,
            )
        except InstagramAPIError as exc:
            config = (
                db.query(RecurringBatchConfig)
                .filter(RecurringBatchConfig.id == config_id)
                .with_for_update()
                .first()
            )
            if not config:
                return

            config.consecutive_failures = (config.consecutive_failures or 0) + 1
            err_msg = str(exc)

            if config.consecutive_failures >= MAX_VIDEO_FAILURES:
                _advance_after_skip(
                    config,
                    len(videos),
                    now,
                    f"Vídeo {index + 1} pulado após {MAX_VIDEO_FAILURES} falhas: {err_msg}",
                )
            else:
                config.last_error = (
                    f"Vídeo {index + 1}/{len(videos)} falhou "
                    f"({config.consecutive_failures}/{MAX_VIDEO_FAILURES}): {err_msg}"
                )
            db.commit()
    except Exception:
        logger.exception("Erro no lote recorrente %s", config_id)
        db.rollback()
    finally:
        db.close()
        lock.release()


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


def kick_recurring_batch(config_id: int) -> None:
    """Dispara o primeiro post imediatamente (ex.: ao clicar Iniciar)."""
    threading.Thread(target=_process_recurring_batch, args=(config_id,), daemon=True).start()


def start_recurring_batch_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Recurring batch worker iniciado")
