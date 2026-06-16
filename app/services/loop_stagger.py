import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Account, LoopConfig, LoopStaggerQueue, RecurringBatchConfig
from app.services.tenancy import get_current_user, scope_accounts
from app.services.video_list import parse_videos_json

logger = logging.getLogger("loop_stagger")

RECOMMENDED_STAGGER_MINUTES_DEV = 15
RECOMMENDED_STAGGER_MINUTES_PROD = 8
RECOMMENDED_VIDEO_INTERVAL_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_account_ids(raw: str) -> list[int]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [int(x) for x in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []


def _loop_ready(loop: LoopConfig | None) -> tuple[bool, str]:
    if not loop:
        return False, "Loop não configurado"
    videos = parse_videos_json(loop.videos_json)
    if not videos:
        return False, "Sem vídeos"
    if not (loop.batch_cover_url or "").strip():
        return False, "Sem capa do lote"
    return True, ""


def _recurring_ready(config: RecurringBatchConfig | None) -> tuple[bool, str]:
    if not config:
        return False, "Lote recorrente não configurado"
    videos = parse_videos_json(config.videos_json)
    if not videos:
        return False, "Sem vídeos"
    if not (config.cover_url or "").strip():
        return False, "Sem capa do lote"
    return True, ""


def activate_continuous_loop(db: Session, account_id: int) -> None:
    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    ready, reason = _loop_ready(loop)
    if not ready:
        raise HTTPException(400, f"Conta #{account_id}: {reason}")

    recurring = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.account_id == account_id).first()
    if recurring and recurring.is_running:
        recurring.is_running = False
        recurring.last_error = "Parado — loop contínuo iniciado via fila escalonada"

    loop.is_running = True
    loop.last_error = ""


def list_loop_candidates(db: Session) -> list[dict]:
    accounts = scope_accounts(db).order_by(Account.id).all()
    result = []
    for account in accounts:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account.id).first()
        ready, reason = _loop_ready(loop)
        result.append({
            "account_id": account.id,
            "name": account.name,
            "username": account.username,
            "ready": ready,
            "reason": reason if not ready else "",
            "is_running": bool(loop and loop.is_running),
            "video_count": len(parse_videos_json(loop.videos_json)) if loop else 0,
        })
    return result


def get_active_queue(db: Session) -> LoopStaggerQueue | None:
    user = get_current_user()
    q = db.query(LoopStaggerQueue).filter(LoopStaggerQueue.is_active.is_(True))
    if user and user.role != "owner":
        q = q.filter(LoopStaggerQueue.owner_user_id == user.id)
    return q.order_by(LoopStaggerQueue.id.desc()).first()


def stop_stagger_queue(db: Session) -> None:
    queue = get_active_queue(db)
    if queue:
        queue.is_active = False
        queue.last_message = "Fila cancelada manualmente"
        queue.next_activation_at = None
        db.commit()


def start_stagger_queue(db: Session, account_ids: list[int], stagger_minutes: int) -> LoopStaggerQueue:
    if len(account_ids) < 1:
        raise HTTPException(400, "Selecione pelo menos 1 conta")
    if stagger_minutes < 3:
        raise HTTPException(400, "Intervalo mínimo entre ativações: 3 minutos")
    if stagger_minutes > 180:
        raise HTTPException(400, "Intervalo máximo: 180 minutos")

    scoped_ids = {a.id for a in scope_accounts(db).all()}
    for account_id in account_ids:
        if account_id not in scoped_ids:
            raise HTTPException(404, f"Conta {account_id} não encontrada")

    seen: set[int] = set()
    ordered: list[int] = []
    for account_id in account_ids:
        if account_id in seen:
            continue
        seen.add(account_id)
        ordered.append(account_id)

    for account_id in ordered:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        ready, reason = _loop_ready(loop)
        if not ready:
            account = db.get(Account, account_id)
            label = account.name if account else f"#{account_id}"
            raise HTTPException(400, f"{label}: {reason}")

    user = get_current_user()
    owner_id = user.id if user else None

    existing = db.query(LoopStaggerQueue).filter(LoopStaggerQueue.is_active.is_(True))
    if user and user.role != "owner":
        existing = existing.filter(LoopStaggerQueue.owner_user_id == user.id)
    for old in existing.all():
        old.is_active = False
        old.last_message = "Substituída por nova fila escalonada"

    now = _utcnow()
    queue = LoopStaggerQueue(
        owner_user_id=owner_id,
        account_ids_json=json.dumps(ordered),
        stagger_minutes=stagger_minutes,
        next_index=1,
        is_active=len(ordered) > 1,
        next_activation_at=(now + timedelta(minutes=stagger_minutes)) if len(ordered) > 1 else None,
        started_at=now,
        last_message=f"1/{len(ordered)} ativo — próximo em {stagger_minutes} min" if len(ordered) > 1 else f"{len(ordered)} loop(s) ativo(s)",
    )
    db.add(queue)

    activate_continuous_loop(db, ordered[0])
    db.commit()
    db.refresh(queue)
    logger.info("Fila escalonada iniciada: %s contas, intervalo %s min", len(ordered), stagger_minutes)
    return queue


def process_stagger_queues(db: Session) -> None:
    now = _utcnow()
    queues = (
        db.query(LoopStaggerQueue)
        .filter(LoopStaggerQueue.is_active.is_(True))
        .all()
    )
    for queue in queues:
        ids = _parse_account_ids(queue.account_ids_json)
        if not ids:
            queue.is_active = False
            continue

        next_at = _normalize_dt(queue.next_activation_at)
        if queue.next_index >= len(ids):
            queue.is_active = False
            queue.next_activation_at = None
            queue.last_message = f"Fila concluída — {len(ids)} loop(s) ativos"
            continue

        if next_at and now < next_at:
            continue

        account_id = ids[queue.next_index]
        account = db.get(Account, account_id)
        label = account.name if account else f"#{account_id}"

        try:
            activate_continuous_loop(db, account_id)
            queue.next_index += 1
            activated = queue.next_index
            total = len(ids)

            if queue.next_index >= total:
                queue.is_active = False
                queue.next_activation_at = None
                queue.last_message = f"Fila concluída — {total} loop(s) ativos"
            else:
                queue.next_activation_at = now + timedelta(minutes=queue.stagger_minutes)
                queue.last_message = (
                    f"{activated}/{total} ativos — próximo ({label}) em {queue.stagger_minutes} min"
                )

            logger.info("Fila escalonada: ativado loop da conta %s (%s/%s)", account_id, activated, total)
        except HTTPException as exc:
            queue.last_message = f"Falha ao ativar {label}: {exc.detail}"
            queue.next_index += 1
            if queue.next_index >= len(ids):
                queue.is_active = False
                queue.next_activation_at = None
            else:
                queue.next_activation_at = now + timedelta(minutes=queue.stagger_minutes)


def stagger_status_dict(db: Session, queue: LoopStaggerQueue | None) -> dict:
    if not queue:
        return {
            "active": False,
            "recommendations": {
                "stagger_minutes_dev": RECOMMENDED_STAGGER_MINUTES_DEV,
                "stagger_minutes_prod": RECOMMENDED_STAGGER_MINUTES_PROD,
                "video_interval_seconds": RECOMMENDED_VIDEO_INTERVAL_SECONDS,
            },
        }

    ids = _parse_account_ids(queue.account_ids_json)
    now = _utcnow()
    next_at = _normalize_dt(queue.next_activation_at)
    wait_seconds = max(0, int((next_at - now).total_seconds())) if next_at and next_at > now else 0

    items = []
    for idx, account_id in enumerate(ids):
        account = db.get(Account, account_id)
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        if idx < queue.next_index:
            state = "ativo"
        elif idx == queue.next_index and queue.is_active:
            state = "proximo"
        else:
            state = "aguardando"
        items.append({
            "account_id": account_id,
            "name": account.name if account else f"#{account_id}",
            "username": account.username if account else "",
            "state": state,
            "is_running": bool(loop and loop.is_running),
        })

    return {
        "active": queue.is_active,
        "id": queue.id,
        "stagger_minutes": queue.stagger_minutes,
        "started_at": queue.started_at.isoformat() if queue.started_at else None,
        "next_activation_at": next_at.isoformat() if next_at else None,
        "wait_seconds": wait_seconds,
        "activated_count": queue.next_index,
        "total_count": len(ids),
        "last_message": queue.last_message,
        "items": items,
        "recommendations": {
            "stagger_minutes_dev": RECOMMENDED_STAGGER_MINUTES_DEV,
            "stagger_minutes_prod": RECOMMENDED_STAGGER_MINUTES_PROD,
            "video_interval_seconds": RECOMMENDED_VIDEO_INTERVAL_SECONDS,
        },
    }
