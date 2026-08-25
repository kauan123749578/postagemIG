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
        "status": a.status,
        "total_posts": a.total_posts,
        "jobs_pending": pending,
        "jobs_posted": posted,
        "jobs_error": errors,
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
            status=status,
        )
        db.add(a)
        db.flush()
        auto_id = a.id
        notify.log_event(f"Automação criada: {name}", "success")
        return {"ok": True, "id": auto_id, "message": "Automação criada (pausada). Ative quando quiser."}


def update_automation_accounts(automation_id: int, account_ids: list[int]) -> dict:
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        if a.status == "active":
            return {"ok": False, "message": "Pause a automação antes de mudar as contas"}
        a.account_ids_json = json.dumps([int(x) for x in account_ids])
        return {"ok": True, "message": "Contas atualizadas"}


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
    with svc.session_scope() as db:
        a = db.get(Automation, automation_id)
        if not a:
            return {"ok": False, "message": "Automação não encontrada"}
        a.status = "paused"
        db.query(AutomationJob).filter(
            AutomationJob.automation_id == a.id,
            AutomationJob.status == "pending",
        ).update({"status": "cancelled"}, synchronize_session=False)
        notify.log_event(f"Automação pausada: {a.name}", "info")
        return {"ok": True, "message": "Pausada"}


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


def process_automation_job(job_id: int) -> bool:
    """Publica um job due. Retorna True se processou."""
    account_id = 0
    video_path = ""
    caption = ""
    cover_path = ""

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
    )

    db = SessionLocal()
    try:
        job = db.get(AutomationJob, job_id)
        auto = db.get(Automation, job.automation_id) if job else None
        if not job:
            return True
        if result.get("ok"):
            job.status = "posted"
            job.media_id = str(result.get("media_id") or "")
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
            out.append({
                "id": a.id,
                "name": a.name or f"Automação #{a.id}",
                "interval_minutes": a.interval_minutes,
                "pending": pending,
                "total_posts": a.total_posts or 0,
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
