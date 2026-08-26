"""Automações estilo Instablack: 1 legenda + N vídeos + 1 capa + N contas + anti-farm."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import notify
from core.db import Account, Automation, AutomationJob, SessionLocal
from core import service as svc


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite devolve naive; normaliza para UTC aware antes de comparar."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_json_list(raw: str) -> list:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _automation_dict(a: Automation, db) -> dict:
    videos = _parse_json_list(a.videos_json)
    account_ids = [int(x) for x in _parse_json_list(a.account_ids_json) if str(x).isdigit() or isinstance(x, int)]
    pending = db.query(AutomationJob).filter(
        AutomationJob.automation_id == a.id,
        AutomationJob.status == "pending",
    ).count()
    posted = db.query(AutomationJob).filter(
        AutomationJob.automation_id == a.id,
        AutomationJob.status == "posted",
    ).count()
    errors = db.query(AutomationJob).filter(
        AutomationJob.automation_id == a.id,
        AutomationJob.status == "error",
    ).count()
    next_job = (
        db.query(AutomationJob)
        .filter(
            AutomationJob.automation_id == a.id,
            AutomationJob.status == "pending",
        )
        .order_by(AutomationJob.scheduled_at)
        .first()
    )
    next_at = ""
    if next_job and next_job.scheduled_at:
        when = next_job.scheduled_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        next_at = when.isoformat()
    accounts = []
    for aid in account_ids:
        acc = db.get(Account, aid)
        if acc:
            accounts.append({
                "id": acc.id,
                "name": acc.name,
                "username": acc.username,
                "status": acc.status,
            })
    return {
        "id": a.id,
        "name": a.name,
        "content_type": a.content_type,
        "caption": a.caption,
        "cover_path": a.cover_path,
        "videos": videos,
        "video_count": len(videos),
        "account_ids": account_ids,
        "accounts": accounts,
        "interval_minutes": a.interval_minutes,
        "stagger_enabled": bool(a.stagger_enabled),
        "stagger_min_minutes": a.stagger_min_minutes,
        "stagger_max_minutes": a.stagger_max_minutes,
        "pin_comment": getattr(a, "pin_comment", "") or "",
        "status": a.status,
        "total_posts": a.total_posts,
        "jobs_pending": pending,
        "jobs_posted": posted,
        "jobs_error": errors,
        "next_at": next_at,
        "last_error": a.last_error,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "activated_at": a.activated_at.isoformat() if a.activated_at else "",
    }


def list_automations() -> list[dict]:
    with svc.session_scope() as db:
        rows = db.query(Automation).order_by(Automation.id.desc()).all()
        return [_automation_dict(a, db) for a in rows]


def get_automation(automation_id: int) -> dict | None:
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        return _automation_dict(a, db) if a else None


def create_automation(
    *,
    name: str,
    caption: str,
    videos: list[str],
    cover_path: str = "",
    account_ids: list[int] | None = None,
    interval_minutes: int = 10,
    stagger_enabled: bool = True,
    stagger_min_minutes: int = 2,
    stagger_max_minutes: int = 8,
    content_type: str = "reel",
    pin_comment: str = "",
) -> dict:
    caption = (caption or "").strip()
    if not caption:
        return {"ok": False, "message": "Legenda obrigatória — sem legenda não cria e não publica."}
    videos = [v for v in (videos or []) if v and Path(v).exists()]
    if not videos:
        return {"ok": False, "message": "Nenhum vídeo selecionado — escolha um ou mais .mp4."}
    if cover_path and not Path(cover_path).exists():
        cover_path = ""
    account_ids = [int(x) for x in (account_ids or [])]
    interval_minutes = max(1, int(interval_minutes or 10))
    stagger_min = max(0, int(stagger_min_minutes or 0))
    stagger_max = max(stagger_min, int(stagger_max_minutes or stagger_min))
    name = (name or "").strip() or f"Reels a cada {interval_minutes} min"
    pin_comment = (pin_comment or "").strip()

    last_err: Exception | None = None
    for attempt in range(5):
        try:
            with svc.session_scope() as db:
                status = "paused" if not account_ids else "paused"
                a = Automation(
                    name=name,
                    content_type=content_type or "reel",
                    caption=caption,
                    cover_path=cover_path or "",
                    videos_json=json.dumps(videos, ensure_ascii=False),
                    account_ids_json=json.dumps(account_ids),
                    interval_minutes=interval_minutes,
                    stagger_enabled=bool(stagger_enabled),
                    stagger_min_minutes=stagger_min,
                    stagger_max_minutes=stagger_max,
                    pin_comment=pin_comment,
                    status=status,
                )
                db.add(a)
                db.flush()
                auto_id = a.id
                notify.log_event(f"Automação criada: {name}", "success")
                return {"ok": True, "id": auto_id, "message": "Automação criada (pausada). Ative quando quiser."}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if "locked" in str(exc).lower() and attempt < 4:
                import time

                time.sleep(0.25 * (attempt + 1))
                continue
            return {"ok": False, "message": f"Erro ao criar: {exc}"}
    return {"ok": False, "message": f"Erro ao criar: {last_err}"}


def _append_jobs_for_accounts(db, a: Automation, new_account_ids: list[int]) -> int:
    """Agenda posts só para contas novas, sem apagar a fila existente."""
    videos = [v for v in _parse_json_list(a.videos_json) if v and Path(v).exists()]
    if not videos or not new_account_ids:
        return 0

    accounts: list[Account] = []
    for aid in new_account_ids:
        acc = db.get(Account, int(aid))
        if acc and acc.is_active and acc.status == "healthy" and acc.session_json:
            accounts.append(acc)
    if not accounts:
        return 0

    cover = a.cover_path if a.cover_path and Path(a.cover_path).exists() else ""
    caption = a.caption
    interval = max(1, int(a.interval_minutes or 10))
    stagger_on = bool(a.stagger_enabled)
    smin = max(0, int(a.stagger_min_minutes or 0))
    smax = max(smin, int(a.stagger_max_minutes or smin))

    last_pending = (
        db.query(AutomationJob.scheduled_at)
        .filter(
            AutomationJob.automation_id == a.id,
            AutomationJob.status == "pending",
        )
        .order_by(AutomationJob.scheduled_at.desc())
        .first()
    )
    now = _now()
    if last_pending and last_pending[0]:
        base = last_pending[0]
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        t = max(base + timedelta(seconds=45), now + timedelta(seconds=45))
    else:
        t = now + timedelta(seconds=30)

    created = 0
    for v_idx, video in enumerate(videos):
        cycle_start = t
        last_t = t
        for a_idx, acc in enumerate(accounts):
            if a_idx == 0:
                when = cycle_start
            elif stagger_on:
                when = last_t + timedelta(minutes=random.uniform(smin, smax) if smax > 0 else 0)
            else:
                when = cycle_start
            db.add(
                AutomationJob(
                    automation_id=a.id,
                    account_id=acc.id,
                    video_path=video,
                    cover_path=cover,
                    caption=caption,
                    video_index=v_idx,
                    account_index=a_idx,
                    scheduled_at=when,
                    status="pending",
                )
            )
            created += 1
            last_t = when
        t = cycle_start + timedelta(minutes=interval)
        if t < last_t + timedelta(seconds=30):
            t = last_t + timedelta(seconds=30)
    return created


def update_automation_accounts(automation_id: int, account_ids: list[int]) -> dict:
    """Atualiza contas da automação. Contas novas entram na fila; removidas saem dos pending."""
    wanted = []
    seen: set[int] = set()
    for x in account_ids or []:
        aid = int(x)
        if aid not in seen:
            seen.add(aid)
            wanted.append(aid)
    if not wanted:
        return {"ok": False, "message": "Selecione pelo menos uma conta"}

    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}

        old = [
            int(x)
            for x in _parse_json_list(a.account_ids_json)
            if str(x).isdigit() or isinstance(x, int)
        ]
        old_set = set(old)
        new_set = set(wanted)
        added = [x for x in wanted if x not in old_set]
        removed = [x for x in old if x not in new_set]

        a.account_ids_json = json.dumps(wanted)

        cancelled = 0
        if removed:
            pending_rm = (
                db.query(AutomationJob)
                .filter(
                    AutomationJob.automation_id == a.id,
                    AutomationJob.status == "pending",
                    AutomationJob.account_id.in_(removed),
                )
                .all()
            )
            for job in pending_rm:
                job.status = "cancelled"
                cancelled += 1

        appended = 0
        if added:
            # se está ativa (ou tem fila), agenda só as novas; se pausada sem fila, só salva a lista
            has_pending = (
                db.query(AutomationJob)
                .filter(
                    AutomationJob.automation_id == a.id,
                    AutomationJob.status == "pending",
                )
                .count()
                > 0
            )
            if a.status == "active" or has_pending:
                appended = _append_jobs_for_accounts(db, a, added)
            elif a.status in ("paused", "draft", "done", "error") and not has_pending:
                # fila vazia: na próxima ativação/retomada o _build_jobs usa a lista nova
                appended = 0

        parts = ["Contas atualizadas"]
        if added:
            if appended:
                parts.append(f"+{len(added)} conta(s) · {appended} post(s) na fila")
            else:
                parts.append(f"+{len(added)} conta(s) (entram ao retomar/ativar)")
        if removed:
            parts.append(f"-{len(removed)} conta(s)" + (f" · {cancelled} cancelado(s)" if cancelled else ""))
        msg = " · ".join(parts)
        notify.log_event(f"Automação editada ({a.name}): {msg}", "info")
        return {
            "ok": True,
            "message": msg,
            "added": len(added),
            "removed": len(removed),
            "jobs_added": appended,
            "jobs_cancelled": cancelled,
        }


def _build_jobs(db, a: Automation) -> int:
    """Gera jobs pending (vídeo × conta) com anti-farm. Apaga jobs pending antigos."""
    db.query(AutomationJob).filter(
        AutomationJob.automation_id == a.id,
        AutomationJob.status == "pending",
    ).delete(synchronize_session=False)

    videos = [v for v in _parse_json_list(a.videos_json) if v and Path(v).exists()]
    account_ids = [int(x) for x in _parse_json_list(a.account_ids_json)]
    if not videos or not account_ids:
        return 0

    # só contas ativas/healthy entram na fila
    accounts: list[Account] = []
    for aid in account_ids:
        acc = db.get(Account, aid)
        if acc and acc.is_active and acc.status == "healthy" and acc.session_json:
            accounts.append(acc)
    if not accounts:
        return 0

    cover = a.cover_path if a.cover_path and Path(a.cover_path).exists() else ""
    caption = a.caption
    interval = max(1, int(a.interval_minutes or 10))
    stagger_on = bool(a.stagger_enabled)
    smin = max(0, int(a.stagger_min_minutes or 0))
    smax = max(smin, int(a.stagger_max_minutes or smin))

    t = _now()
    created = 0
    for v_idx, video in enumerate(videos):
        cycle_start = t
        last_t = t
        for a_idx, acc in enumerate(accounts):
            if a_idx == 0:
                when = cycle_start
            elif stagger_on:
                when = last_t + timedelta(minutes=random.uniform(smin, smax) if smax > 0 else 0)
            else:
                when = cycle_start
            job = AutomationJob(
                automation_id=a.id,
                account_id=acc.id,
                video_path=video,
                cover_path=cover,
                caption=caption,
                video_index=v_idx,
                account_index=a_idx,
                scheduled_at=when,
                status="pending",
            )
            db.add(job)
            created += 1
            last_t = when
        # próximo vídeo: no mínimo interval após o início deste ciclo
        t = cycle_start + timedelta(minutes=interval)
        if t < last_t + timedelta(seconds=30):
            t = last_t + timedelta(seconds=30)
    return created


def activate_automation(automation_id: int) -> dict:
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        if not (a.caption or "").strip():
            return {"ok": False, "message": "Legenda obrigatória"}
        videos = [v for v in _parse_json_list(a.videos_json) if Path(v).exists()]
        if not videos:
            return {"ok": False, "message": "Nenhum vídeo válido"}
        account_ids = _parse_json_list(a.account_ids_json)
        if not account_ids:
            return {"ok": False, "message": "Selecione pelo menos uma conta antes de ativar"}

        n = _build_jobs(db, a)
        if n == 0:
            return {
                "ok": False,
                "message": "Nenhuma conta saudável com sessão para agendar. Reconecte em Contas.",
            }
        a.status = "active"
        a.activated_at = _now()
        a.last_error = ""
        db.flush()
        notify.log_event(f"Automação ativada: {a.name} ({n} posts na fila)", "success")
        return {"ok": True, "message": f"Ativada — {n} publicações agendadas", "jobs": n}


def pause_automation(automation_id: int) -> dict:
    """Pausa sem apagar a fila — jobs pending ficam congelados até Retomar."""
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        if a.status != "active":
            return {"ok": False, "message": "Só dá para pausar automações ativas"}
        pending = db.query(AutomationJob).filter(
            AutomationJob.automation_id == a.id,
            AutomationJob.status == "pending",
        ).count()
        a.status = "paused"
        notify.log_event(
            f"Automação pausada: {a.name} ({pending} post(s) na fila, prontos para retomar)",
            "info",
        )
        return {"ok": True, "message": f"Pausada — {pending} post(s) guardados na fila", "pending": pending}


def _redistribute_jobs(
    a: Automation,
    jobs: list[AutomationJob],
    *,
    start: datetime | None = None,
) -> datetime:
    """Reagenda a fila pending com o intervalo e anti-farm da automação (a partir de agora)."""
    if not jobs:
        return start or _now()

    interval = max(1, int(a.interval_minutes or 10))
    stagger_on = bool(a.stagger_enabled)
    smin = max(0, int(a.stagger_min_minutes or 0))
    smax = max(smin, int(a.stagger_max_minutes or smin))

    ordered = sorted(
        jobs,
        key=lambda j: (int(j.video_index or 0), int(j.account_index or 0), int(j.id or 0)),
    )
    by_video: dict[int, list[AutomationJob]] = {}
    for job in ordered:
        by_video.setdefault(int(job.video_index or 0), []).append(job)

    t = start or _now()
    last_overall = t
    for v_idx in sorted(by_video.keys()):
        group = by_video[v_idx]
        cycle_start = t
        last_t = t
        for a_idx, job in enumerate(group):
            if a_idx == 0:
                when = cycle_start
            elif stagger_on and smax > 0:
                when = last_t + timedelta(minutes=random.uniform(smin, smax))
            else:
                when = cycle_start
            job.scheduled_at = when
            last_t = when
            last_overall = when
        t = cycle_start + timedelta(minutes=interval)
        if t < last_t + timedelta(seconds=30):
            t = last_t + timedelta(seconds=30)
    return last_overall


def resume_automation(automation_id: int) -> dict:
    """Retoma automação pausada e reaplica o intervalo configurado na fila."""
    now = _now()
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        if a.status not in ("paused", "done", "draft", "error"):
            if a.status == "active":
                return {"ok": False, "message": "Já está ativa"}
            return {"ok": False, "message": f"Status inválido para retomar: {a.status}"}

        pending_jobs = (
            db.query(AutomationJob)
            .filter(
                AutomationJob.automation_id == a.id,
                AutomationJob.status == "pending",
            )
            .order_by(AutomationJob.scheduled_at, AutomationJob.id)
            .all()
        )

        # Se não sobrou fila, remonta a partir dos vídeos/contas
        if not pending_jobs:
            n = _build_jobs(db, a)
            if n == 0:
                return {
                    "ok": False,
                    "message": "Sem posts na fila e não deu para remontar. Reconecte contas ou confira os vídeos.",
                }
            a.status = "active"
            a.activated_at = now
            a.last_error = ""
            notify.log_event(f"Automação retomada (nova fila): {a.name} ({n} posts)", "success")
            return {"ok": True, "message": f"Retomada — {n} publicações agendadas", "jobs": n}

        # Redistribui TODA a fila com o intervalo da automação (ex.: 30 min + anti-farm)
        _redistribute_jobs(a, pending_jobs, start=now)
        interval = max(1, int(a.interval_minutes or 10))

        a.status = "active"
        a.last_error = ""
        if not a.activated_at:
            a.activated_at = now
        notify.log_event(
            f"Automação retomada: {a.name} ({len(pending_jobs)} post(s), a cada {interval} min)",
            "success",
        )
        return {
            "ok": True,
            "message": f"Retomada — {len(pending_jobs)} post(s) na fila (a cada {interval} min)",
            "jobs": len(pending_jobs),
        }


def delete_automation(automation_id: int) -> dict:
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        name = a.name
        db.delete(a)
        notify.log_event(f"Automação removida: {name}", "info")
        return {"ok": True, "message": "Removida"}


def list_due_automation_job_ids(limit: int = 5) -> list[int]:
    now = _now()
    db = SessionLocal()
    try:
        rows = (
            db.query(AutomationJob.id)
            .join(Automation, Automation.id == AutomationJob.automation_id)
            .filter(
                Automation.status == "active",
                AutomationJob.status == "pending",
                AutomationJob.scheduled_at <= now,
            )
            .order_by(AutomationJob.scheduled_at)
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]
    finally:
        db.close()


def reschedule_overdue_jobs_on_startup() -> dict:
    """Ao reabrir o app: se houver posts atrasados, redistribui com o intervalo da automação."""
    now = _now()
    with svc.session_scope() as db:
        overdue = (
            db.query(AutomationJob)
            .join(Automation, Automation.id == AutomationJob.automation_id)
            .filter(
                Automation.status == "active",
                AutomationJob.status == "pending",
                AutomationJob.scheduled_at < now,
            )
            .order_by(AutomationJob.scheduled_at, AutomationJob.id)
            .all()
        )
        if not overdue:
            pending_future = (
                db.query(AutomationJob)
                .join(Automation, Automation.id == AutomationJob.automation_id)
                .filter(
                    Automation.status == "active",
                    AutomationJob.status == "pending",
                    AutomationJob.scheduled_at >= now,
                )
                .count()
            )
            active = db.query(Automation).filter(Automation.status == "active").count()
            return {
                "overdue_rescheduled": 0,
                "pending_future": pending_future,
                "automations_active": active,
            }

        # Por automação: redistribui toda a fila pending com interval_minutes
        auto_ids = {job.automation_id for job in overdue}
        total_moved = 0
        for aid in auto_ids:
            a = db.get(Automation, aid)
            if not a:
                continue
            pending = (
                db.query(AutomationJob)
                .filter(
                    AutomationJob.automation_id == aid,
                    AutomationJob.status == "pending",
                )
                .all()
            )
            _redistribute_jobs(a, pending, start=now)
            total_moved += len(pending)

        active = db.query(Automation).filter(Automation.status == "active").count()
        pending_future = (
            db.query(AutomationJob)
            .join(Automation, Automation.id == AutomationJob.automation_id)
            .filter(
                Automation.status == "active",
                AutomationJob.status == "pending",
            )
            .count()
        )
        notify.log_event(
            f"Retomada: {total_moved} post(s) redistribuído(s) com o intervalo das automações "
            f"· {active} ativa(s)",
            "info",
        )
        return {
            "overdue_rescheduled": total_moved,
            "pending_future": pending_future,
            "automations_active": active,
        }


def process_automation_job(job_id: int) -> bool:
    """Publica um job due. Retorna True se processou."""
    account_id = 0
    video_path = ""
    caption = ""
    cover_path = ""
    pin_comment = ""

    db = SessionLocal()
    try:
        job = db.get(AutomationJob, job_id)
        if not job or job.status != "pending":
            return False
        auto = db.get(Automation, job.automation_id)
        if not auto or auto.status != "active":
            job.status = "cancelled"
            db.commit()
            return True
        sched = _aware(job.scheduled_at)
        if sched and sched > _now():
            return False

        acc = db.get(Account, job.account_id)
        if not acc or not acc.is_active or acc.status != "healthy":
            job.status = "skipped"
            job.error_message = "Conta indisponível / sessão inválida"
            db.commit()
            return True

        account_id = job.account_id
        video_path = job.video_path
        caption = job.caption or ""
        cover_path = job.cover_path or ""
        pin_comment = (getattr(auto, "pin_comment", None) or "").strip()
    finally:
        db.close()

    if not account_id or not video_path:
        return False

    # post fora da sessão ORM longa
    result = svc.post_reel_now(
        account_id,
        video_path,
        caption,
        cover_path or None,
        pin_comment=pin_comment or None,
    )

    db = SessionLocal()
    try:
        job = db.get(AutomationJob, job_id)
        auto = db.get(Automation, job.automation_id) if job else None
        if not job:
            return True
        if result.get("ok"):
            job.status = "posted"
            job.media_id = str(result.get("media_pk") or result.get("media_id") or "")
            job.posted_at = _now()
            if auto:
                auto.total_posts = int(auto.total_posts or 0) + 1
                auto.last_error = ""
        else:
            job.status = "error"
            job.error_message = result.get("message") or "Erro ao publicar"
            if auto:
                auto.last_error = job.error_message

        # se não sobrou pending, marca done
        if auto and auto.status == "active":
            left = db.query(AutomationJob).filter(
                AutomationJob.automation_id == auto.id,
                AutomationJob.status == "pending",
            ).count()
            if left == 0:
                auto.status = "done"
                notify.log_event(f"Automação concluída: {auto.name}", "success")

        db.commit()
    finally:
        db.close()
    return True


def automation_stats() -> dict:
    with svc.session_scope() as db:
        active = db.query(Automation).filter(Automation.status == "active").count()
        pending = db.query(AutomationJob).filter(AutomationJob.status == "pending").count()
        return {"automations_active": active, "jobs_pending": pending}


def list_active_automations_summary(limit: int = 8) -> list[dict]:
    from sqlalchemy import func

    with svc.session_scope() as db:
        rows = (
            db.query(Automation)
            .filter(Automation.status == "active")
            .order_by(Automation.id.desc())
            .limit(limit)
            .all()
        )
        out = []
        for a in rows:
            pending = db.query(AutomationJob).filter(
                AutomationJob.automation_id == a.id,
                AutomationJob.status == "pending",
            ).count()
            posted_total = db.query(AutomationJob).filter(
                AutomationJob.automation_id == a.id,
                AutomationJob.status == "posted",
            ).count()
            per_acc_rows = (
                db.query(Account.name, Account.username, func.count(AutomationJob.id))
                .join(AutomationJob, AutomationJob.account_id == Account.id)
                .filter(
                    AutomationJob.automation_id == a.id,
                    AutomationJob.status == "posted",
                )
                .group_by(Account.id)
                .order_by(func.count(AutomationJob.id).desc())
                .all()
            )
            posted_by_account = [
                {"name": n or u or "Conta", "username": u or "", "count": int(c)}
                for n, u, c in per_acc_rows
            ]
            next_job = (
                db.query(AutomationJob)
                .filter(
                    AutomationJob.automation_id == a.id,
                    AutomationJob.status == "pending",
                )
                .order_by(AutomationJob.scheduled_at)
                .first()
            )
            next_at = ""
            if next_job and next_job.scheduled_at:
                when = next_job.scheduled_at
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                next_at = when.isoformat()
            out.append({
                "id": a.id,
                "name": a.name or f"Automação #{a.id}",
                "interval_minutes": a.interval_minutes,
                "pending": pending,
                "total_posts": posted_total,
                "posted_by_account": posted_by_account,
                "next_at": next_at,
            })
        return out


def list_upcoming_jobs(limit: int = 8) -> list[dict]:
    with svc.session_scope() as db:
        rows = (
            db.query(AutomationJob, Automation, Account)
            .join(Automation, Automation.id == AutomationJob.automation_id)
            .join(Account, Account.id == AutomationJob.account_id)
            .filter(
                Automation.status == "active",
                AutomationJob.status == "pending",
            )
            .order_by(AutomationJob.scheduled_at)
            .limit(limit)
            .all()
        )
        out = []
        for job, auto, acc in rows:
            when = job.scheduled_at
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            out.append({
                "id": job.id,
                "automation": auto.name or f"#{auto.id}",
                "account": acc.name or acc.username or f"#{acc.id}",
                "username": acc.username or "",
                "scheduled_at": when.isoformat() if when else "",
                "video": Path(job.video_path).name if job.video_path else "",
            })
        return out
