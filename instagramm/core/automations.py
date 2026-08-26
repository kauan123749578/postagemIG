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
        "trial_reels": bool(getattr(a, "trial_reels", False)),
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
    trial_reels: bool = False,
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
    trial_reels = bool(trial_reels)

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
                    trial_reels=trial_reels,
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


def resume_automation(automation_id: int, *, gap_seconds: int = 90) -> dict:
    """Retoma automação pausada: status active + redistribui jobs atrasados."""
    now = _now()
    gap = max(30, int(gap_seconds))
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

        cursor = now
        for job in pending_jobs:
            if job.scheduled_at < now:
                job.scheduled_at = cursor
                cursor = cursor + timedelta(seconds=gap)

        a.status = "active"
        a.last_error = ""
        if not a.activated_at:
            a.activated_at = now
        notify.log_event(
            f"Automação retomada: {a.name} ({len(pending_jobs)} post(s) na fila)",
            "success",
        )
        return {
            "ok": True,
            "message": f"Retomada — {len(pending_jobs)} post(s) na fila",
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


def reschedule_overdue_jobs_on_startup(*, gap_seconds: int = 90) -> dict:
    """Ao reabrir o app: jobs atrasados (PC off) são redistribuídos a partir de agora.

    Mantém automações active e a fila pending — só evita rajada de posts de uma vez.
    """
    now = _now()
    gap = max(30, int(gap_seconds))
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

        cursor = now
        for job in overdue:
            job.scheduled_at = cursor
            cursor = cursor + timedelta(seconds=gap)

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
            f"Retomada: {len(overdue)} post(s) atrasado(s) redistribuído(s) "
            f"(~{gap}s entre cada) · {active} automação(ões) ativa(s)",
            "info",
        )
        return {
            "overdue_rescheduled": len(overdue),
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
    trial = False

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
        sched = job.scheduled_at
        if sched and sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
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
        trial = bool(getattr(auto, "trial_reels", False))
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
        trial=trial,
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
                "total_posts": a.total_posts or 0,
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
