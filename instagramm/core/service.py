"""Camada de serviço: contas, mídia, publicação e estatísticas.

Cada operação abre sua própria sessão de banco e devolve dados simples (dicts),
para a interface não depender de objetos ORM presos a uma sessão.
"""
import json
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import instagram as ig
from core import metrics, notify
from core.config import (
    IMAGE_EXTENSIONS,
    IMAGES_DIR,
    INSTAGRAM_CAPTION_MAX,
    SESSIONS_DIR,
    VIDEO_EXTENSIONS,
    VIDEOS_DIR,
)
from core.crypto import decrypt_secret, encrypt_secret
from core.proxy import normalize_proxy_url
from core.db import (
    Account,
    LoopConfig,
    PostLog,
    ScheduledPost,
    SessionLocal,
    StaggerItem,
    WarmConfig,
    init_db,
)

# device/uuids guardados entre a 1ª tentativa e o envio do código 2FA
_pending_2fa: dict[int, dict] = {}


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def setup() -> None:
    init_db()


def _export_session_file(username: str, settings: dict) -> None:
    """Salva a sessão também como arquivo em data/sessions (além do banco)."""
    try:
        if not username:
            return
        safe = "".join(c for c in username if c.isalnum() or c in "._-") or "conta"
        (SESSIONS_DIR / f"{safe}.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def recent_events(limit: int = 80) -> list[dict]:
    """Eventos do sistema (conexões, posts, aquecimento, erros)."""
    return notify.recent_events(limit)


# ---------------- Contas ----------------

def _account_dict(acc: Account, db) -> dict:
    stats = usage_stats(db, acc.id, acc.max_posts_per_day, acc.max_posts_per_hour)
    loop = acc.loop
    return {
        "id": acc.id,
        "name": acc.name,
        "username": acc.username,
        "proxy_url": acc.proxy_url,
        "default_caption": acc.default_caption,
        "max_posts_per_day": acc.max_posts_per_day,
        "max_posts_per_hour": acc.max_posts_per_hour,
        "is_active": acc.is_active,
        "status": acc.status,
        "status_message": acc.status_message,
        "has_session": bool(acc.session_json),
        "has_password": bool(acc.password_enc),
        "usage": stats,
        "loop_running": bool(loop and loop.is_running),
        "loop_posts": loop.total_posts if loop else 0,
    }


def list_accounts() -> list[dict]:
    with session_scope() as db:
        return [_account_dict(a, db) for a in db.query(Account).order_by(Account.id).all()]


def get_account(account_id: int) -> dict | None:
    with session_scope() as db:
        acc = db.get(Account, account_id)
        return _account_dict(acc, db) if acc else None


def create_account(
    *,
    name: str,
    username: str = "",
    password: str = "",
    proxy_url: str = "",
    default_caption: str = "",
    max_posts_per_day: int = 0,
    max_posts_per_hour: int = 0,
) -> int:
    with session_scope() as db:
        acc = Account(
            name=name.strip(),
            username=(username or "").strip().lstrip("@").lower(),
            proxy_url=normalize_proxy_url(proxy_url),
            default_caption=default_caption[:INSTAGRAM_CAPTION_MAX],
            max_posts_per_day=max(0, int(max_posts_per_day or 0)),
            max_posts_per_hour=max(0, int(max_posts_per_hour or 0)),
        )
        if password:
            acc.password_enc = encrypt_secret(password)
        db.add(acc)
        db.flush()
        return acc.id


def update_account(account_id: int, **fields) -> None:
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return
        if "password" in fields:
            pwd = fields.pop("password")
            if pwd:
                acc.password_enc = encrypt_secret(pwd)
        if "username" in fields and fields["username"] is not None:
            fields["username"] = fields["username"].strip().lstrip("@").lower()
        if "proxy_url" in fields and fields["proxy_url"] is not None:
            fields["proxy_url"] = normalize_proxy_url(fields["proxy_url"])
        if "default_caption" in fields and fields["default_caption"] is not None:
            fields["default_caption"] = fields["default_caption"][:INSTAGRAM_CAPTION_MAX]
        for key, value in fields.items():
            if hasattr(acc, key):
                setattr(acc, key, value)


def delete_account(account_id: int) -> None:
    _pending_2fa.pop(account_id, None)
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)


def connect_account(
    account_id: int,
    *,
    password: str | None = None,
    sessionid: str | None = None,
    verification_code: str | None = None,
) -> dict:
    """Tenta logar. Retorna {status: connected|needs_2fa|error, message}."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"status": "error", "message": "Conta não encontrada"}

        if password:
            acc.password_enc = encrypt_secret(password)
            db.flush()
        pwd = password or decrypt_secret(acc.password_enc) or None

        # reaproveita device da 1ª tentativa quando enviando o código 2FA
        settings = _pending_2fa.get(account_id)
        if not settings and acc.session_json:
            try:
                settings = json.loads(acc.session_json)
            except json.JSONDecodeError:
                settings = None

        try:
            result = ig.login(
                username=acc.username,
                password=pwd,
                sessionid=sessionid,
                verification_code=verification_code,
                proxy_url=acc.proxy_url,
                settings=settings if not (sessionid and sessionid.strip()) else None,
            )
        except ig.InstagramError as exc:
            if exc.kind == "two_factor":
                if exc.settings:
                    _pending_2fa[account_id] = exc.settings
                acc.status = "pending"
                acc.status_message = "Aguardando código 2FA"
                return {"status": "needs_2fa", "message": str(exc)}
            acc.status = "error"
            acc.status_message = str(exc)
            return {"status": "error", "message": str(exc)}

        _pending_2fa.pop(account_id, None)
        acc.session_json = json.dumps(result["settings"])
        acc.username = result.get("username") or acc.username
        acc.status = "healthy"
        acc.status_message = "Conectada"
        _export_session_file(acc.username, result["settings"])
        notify.log_event("Conta conectada", "success", acc.name)
        return {"status": "connected", "message": "Conta conectada com sucesso"}


def check_account(account_id: int) -> dict:
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"status": "error", "message": "Conta não encontrada"}
        try:
            result = ig.verify_session(acc)
            acc.session_json = json.dumps(result["settings"])
            acc.status = "healthy"
            acc.status_message = "Conectada"
            _export_session_file(acc.username, result["settings"])
            return {"status": "healthy", "message": "Sessão válida"}
        except ig.InstagramError as exc:
            acc.status = "error"
            acc.status_message = str(exc)
            return {"status": "error", "message": str(exc)}


# ---------------- Mídia ----------------

def _import_file(src: str, dest_dir: Path, allowed: set[str]) -> str:
    src_path = Path(src.strip().strip('"').strip("'"))
    if not src_path.exists():
        raise ValueError(f"Arquivo não encontrado: {src_path.name}")
    ext = src_path.suffix.lower()
    if ext not in allowed:
        raise ValueError(f"Formato não suportado: {ext}")
    safe = f"{uuid.uuid4().hex}{ext}"
    dest = dest_dir / safe
    shutil.copy2(src_path, dest)
    return str(dest)


def import_video(src: str) -> str:
    return _import_file(src, VIDEOS_DIR, VIDEO_EXTENSIONS)


def import_image(src: str) -> str:
    return _import_file(src, IMAGES_DIR, IMAGE_EXTENSIONS)


def list_media() -> dict:
    def _scan(folder: Path) -> list[dict]:
        items = []
        for p in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file():
                items.append({
                    "path": str(p),
                    "name": p.name,
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                })
        return items
    return {"videos": _scan(VIDEOS_DIR), "images": _scan(IMAGES_DIR)}


# ---------------- Publicação ----------------

def usage_stats(db, account_id: int, max_day: int, max_hour: int) -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    hour_ago = now - timedelta(hours=1)
    posts_24h = db.query(PostLog).filter(
        PostLog.account_id == account_id,
        PostLog.status == "success",
        PostLog.posted_at >= day_ago,
    ).count()
    posts_1h = db.query(PostLog).filter(
        PostLog.account_id == account_id,
        PostLog.status == "success",
        PostLog.posted_at >= hour_ago,
    ).count()
    return {
        "posts_last_24h": posts_24h,
        "posts_last_hour": posts_1h,
        "unlimited_day": max_day == 0,
        "unlimited_hour": max_hour == 0,
        "blocked_day": max_day > 0 and posts_24h >= max_day,
        "blocked_hour": max_hour > 0 and posts_1h >= max_hour,
    }


def can_post(account_id: int) -> tuple[bool, str]:
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return False, "Conta não encontrada"
        if not acc.is_active:
            return False, "Conta inativa"
        stats = usage_stats(db, account_id, acc.max_posts_per_day, acc.max_posts_per_hour)
        if stats["blocked_hour"]:
            return False, "Limite por hora atingido"
        if stats["blocked_day"]:
            return False, "Limite diário atingido"
        return True, "ok"


def post_reel_now(account_id: int, video_path: str, caption: str = "", cover_path: str | None = None) -> dict:
    """Publica um Reel imediatamente e registra no log."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"ok": False, "message": "Conta não encontrada"}
        final_caption = caption or acc.default_caption or ""
        try:
            result = ig.post_reel(acc, video_path, final_caption, cover_path)
            acc.session_json = json.dumps(result["settings"])
            _export_session_file(acc.username, result["settings"])
            db.add(PostLog(
                account_id=acc.id,
                media_id=result["media_pk"],
                media_type="reel",
                caption_preview=final_caption[:300],
                video_path=video_path,
                status="success",
            ))
            link = f"https://instagram.com/reel/{result.get('code')}" if result.get("code") else ""
            metrics.bump("post")
            notify.log_event(f"Reel publicado 🎬 {link}".strip(), "success", acc.name)
            return {"ok": True, "media_pk": result["media_pk"], "code": result.get("code", "")}
        except ig.InstagramError as exc:
            db.add(PostLog(
                account_id=acc.id,
                media_type="reel",
                video_path=video_path,
                status="error",
                error_message=str(exc),
            ))
            acc.status = "error" if exc.kind != "rate_limit" else acc.status
            acc.status_message = str(exc)
            metrics.bump("error")
            notify.log_event(f"Falha ao publicar Reel: {exc}", "error", acc.name)
            return {"ok": False, "message": str(exc), "kind": exc.kind}


def recent_logs(limit: int = 50) -> list[dict]:
    with session_scope() as db:
        rows = (
            db.query(PostLog, Account.name)
            .join(Account, PostLog.account_id == Account.id)
            .order_by(PostLog.posted_at.desc())
            .limit(limit)
            .all()
        )
        return [{
            "account": name,
            "media_type": log.media_type,
            "status": log.status,
            "caption": log.caption_preview,
            "error": log.error_message,
            "media_pk": log.media_id,
            "posted_at": log.posted_at.isoformat() if log.posted_at else "",
        } for log, name in rows]


# ---------------- Loop config ----------------

def get_loop(account_id: int) -> dict:
    with session_scope() as db:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        if not loop:
            return {
                "videos": [], "interval_seconds": 120, "caption": "", "is_running": False,
                "total_posts": 0, "current_index": 0, "mode": "continuo",
                "batch_size": 3, "batch_interval_minutes": 360,
            }
        return {
            "videos": json.loads(loop.videos_json or "[]"),
            "interval_seconds": loop.interval_seconds,
            "caption": loop.caption,
            "is_running": loop.is_running,
            "total_posts": loop.total_posts,
            "current_index": loop.current_index,
            "last_error": loop.last_error,
            "mode": loop.mode or "continuo",
            "batch_size": loop.batch_size or 3,
            "batch_interval_minutes": loop.batch_interval_minutes or 360,
        }


def save_loop(
    account_id: int,
    videos: list[dict],
    interval_seconds: int,
    caption: str = "",
    *,
    mode: str = "continuo",
    batch_size: int = 3,
    batch_interval_minutes: int = 360,
) -> None:
    with session_scope() as db:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        if not loop:
            loop = LoopConfig(account_id=account_id)
            db.add(loop)
        new_videos = json.dumps(videos)
        if loop.videos_json != new_videos:
            loop.current_index = 0
        loop.videos_json = new_videos
        loop.interval_seconds = max(30, int(interval_seconds))
        loop.caption = caption
        loop.mode = mode if mode in ("continuo", "recorrente") else "continuo"
        loop.batch_size = max(1, int(batch_size or 1))
        loop.batch_interval_minutes = max(5, int(batch_interval_minutes or 5))


def set_loop_running(account_id: int, running: bool) -> None:
    with session_scope() as db:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        if not loop:
            loop = LoopConfig(account_id=account_id)
            db.add(loop)
        loop.is_running = running
        if running:
            loop.next_run_at = datetime.now(timezone.utc)
            loop.last_error = ""
            loop.batch_remaining = 0
            loop.current_index = 0
        acc = db.get(Account, account_id)
        name = acc.name if acc else ""
        mode = loop.mode or "continuo"
    label = "Loop recorrente" if mode == "recorrente" else "Loop contínuo"
    notify.log_event(label + (" iniciado" if running else " parado"), "info", name)


# ---------------- Agendamentos ----------------

def add_scheduled(account_id: int, video_path: str, scheduled_at: datetime, caption: str = "", cover_path: str = "") -> None:
    with session_scope() as db:
        db.add(ScheduledPost(
            account_id=account_id,
            video_path=video_path,
            cover_path=cover_path or "",
            caption=caption,
            scheduled_at=scheduled_at,
            status="pending",
        ))


def list_scheduled() -> list[dict]:
    with session_scope() as db:
        rows = (
            db.query(ScheduledPost, Account.name)
            .join(Account, ScheduledPost.account_id == Account.id)
            .order_by(ScheduledPost.scheduled_at)
            .all()
        )
        return [{
            "id": s.id,
            "account": name,
            "video_name": Path(s.video_path).name if s.video_path else "",
            "caption": s.caption,
            "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else "",
            "status": s.status,
            "error": s.error_message,
        } for s, name in rows]


def cancel_scheduled(post_id: int) -> None:
    with session_scope() as db:
        post = db.get(ScheduledPost, post_id)
        if post and post.status == "pending":
            post.status = "cancelled"


def dashboard_stats() -> dict:
    with session_scope() as db:
        total = db.query(Account).count()
        connected = db.query(Account).filter(Account.status == "healthy").count()
        loops = db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).count()
        warming = db.query(WarmConfig).filter(WarmConfig.is_running.is_(True)).count()
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        posts_today = db.query(PostLog).filter(PostLog.status == "success", PostLog.posted_at >= day_ago).count()
        pending = db.query(ScheduledPost).filter(ScheduledPost.status == "pending").count()
        return {
            "accounts": total,
            "connected": connected,
            "loops_running": loops,
            "warming": warming,
            "posts_24h": posts_today,
            "scheduled_pending": pending,
        }


# ---------------- Gráficos / métricas ----------------

WARM_KEYS = ["like", "comment", "follow", "unfollow", "story_view", "story_like", "save", "scroll"]


def chart_data(days: int = 7) -> dict:
    """Dados agregados para os gráficos do dashboard."""
    posts = metrics.series("post", days)
    warm = metrics.series_sum(WARM_KEYS, days)
    errors = metrics.series("error", days)
    breakdown = metrics.totals(WARM_KEYS, days)
    return {
        "posts": posts,
        "warm": warm,
        "errors": errors,
        "breakdown": breakdown,
    }


# ---------------- Fila escalonada ----------------

def start_stagger(account_ids: list[int], stagger_minutes: int = 10) -> dict:
    """Agenda a ativação dos loops das contas, uma a cada X minutos."""
    if not account_ids:
        return {"ok": False, "message": "Selecione ao menos uma conta"}
    step = max(1, int(stagger_minutes))
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        # limpa fila pendente anterior
        db.query(StaggerItem).filter(StaggerItem.status == "pending").update({"status": "cancelled"})
        for i, acc_id in enumerate(account_ids):
            db.add(StaggerItem(account_id=acc_id, activate_at=now + timedelta(minutes=step * i), status="pending"))
    notify.log_event(f"Fila escalonada iniciada: {len(account_ids)} contas, 1 a cada {step} min", "info")
    return {"ok": True, "message": f"{len(account_ids)} contas na fila"}


def list_stagger() -> list[dict]:
    with session_scope() as db:
        rows = (
            db.query(StaggerItem, Account.name)
            .join(Account, StaggerItem.account_id == Account.id)
            .filter(StaggerItem.status.in_(["pending", "activated"]))
            .order_by(StaggerItem.activate_at)
            .all()
        )
        return [{
            "id": s.id,
            "account": name,
            "activate_at": s.activate_at.isoformat() if s.activate_at else "",
            "status": s.status,
        } for s, name in rows]


def cancel_stagger() -> None:
    with session_scope() as db:
        db.query(StaggerItem).filter(StaggerItem.status == "pending").update({"status": "cancelled"})
    notify.log_event("Fila escalonada cancelada", "info")


# ---------------- Importar sessão ----------------

def import_session(name: str, path: str, proxy_url: str = "") -> dict:
    """Cria uma conta a partir de um arquivo session.json da instagrapi."""
    proxy_norm = normalize_proxy_url(proxy_url)
    try:
        result = ig.load_session_file(path, proxy_norm or None)
    except ig.InstagramError as exc:
        return {"status": "error", "message": str(exc)}

    with session_scope() as db:
        username = result.get("username") or ""
        acc = db.query(Account).filter(Account.username == username).first() if username else None
        if not acc:
            acc = Account(name=name.strip() or username or "Conta", username=username)
            db.add(acc)
            db.flush()
        acc.proxy_url = proxy_norm
        acc.session_json = json.dumps(result["settings"])
        acc.username = username or acc.username
        acc.status = "healthy"
        acc.status_message = "Sessão importada"
        _export_session_file(acc.username, result["settings"])
        notify.log_event("Sessão importada com sucesso", "success", acc.name)
        return {"status": "connected", "message": f"Conta @{username} importada", "account_id": acc.id}


# ---------------- Aquecimento ----------------

_WARM_FIELDS = (
    "likes_per_run", "stories_per_run", "follows_per_run", "saves_per_run",
    "comments_per_run", "story_likes_per_run", "unfollows_per_run", "scrolls_per_run",
    "interval_minutes",
)
_WARM_HOUR_FIELDS = ("active_start_hour", "active_end_hour")


def within_active_window(start_hour: int, end_hour: int, now_hour: int | None = None) -> bool:
    """Verifica se a hora local atual está dentro da janela de aquecimento."""
    if now_hour is None:
        now_hour = datetime.now().hour
    start = max(0, min(23, int(start_hour)))
    end = max(0, min(24, int(end_hour)))
    if start == end:
        return True  # janela de 24h
    if start < end:
        return start <= now_hour < end
    # janela que cruza a meia-noite (ex.: 22 -> 6)
    return now_hour >= start or now_hour < end


def get_warm(account_id: int) -> dict:
    with session_scope() as db:
        w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
        if not w:
            return {
                # preset recomendado: já pronto para apenas apertar "Iniciar"
                "likes_per_run": 5, "stories_per_run": 5, "follows_per_run": 1, "saves_per_run": 1,
                "comments_per_run": 1, "story_likes_per_run": 2, "unfollows_per_run": 0, "scrolls_per_run": 2,
                "interval_minutes": 40, "hashtags": "reels,explore,viral,foryou,fyp",
                "active_start_hour": 8, "active_end_hour": 23,
                "is_running": False, "total_actions": 0, "last_summary": "", "last_error": "",
            }
        return {
            "likes_per_run": w.likes_per_run, "stories_per_run": w.stories_per_run,
            "follows_per_run": w.follows_per_run, "saves_per_run": w.saves_per_run,
            "comments_per_run": w.comments_per_run or 0, "story_likes_per_run": w.story_likes_per_run or 0,
            "unfollows_per_run": w.unfollows_per_run or 0, "scrolls_per_run": w.scrolls_per_run or 1,
            "interval_minutes": w.interval_minutes, "hashtags": w.hashtags,
            "active_start_hour": w.active_start_hour if w.active_start_hour is not None else 8,
            "active_end_hour": w.active_end_hour if w.active_end_hour is not None else 23,
            "is_running": w.is_running, "total_actions": w.total_actions,
            "last_summary": w.last_summary, "last_error": w.last_error,
        }


def save_warm(account_id: int, **cfg) -> None:
    with session_scope() as db:
        w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
        if not w:
            w = WarmConfig(account_id=account_id)
            db.add(w)
        for key in _WARM_FIELDS:
            if key in cfg and cfg[key] is not None:
                setattr(w, key, max(0, int(cfg[key])))
        for key in _WARM_HOUR_FIELDS:
            if key in cfg and cfg[key] is not None:
                setattr(w, key, max(0, min(24, int(cfg[key]))))
        if "hashtags" in cfg and cfg["hashtags"] is not None:
            w.hashtags = cfg["hashtags"]
        w.interval_minutes = max(5, w.interval_minutes or 45)


def save_warm_many(account_ids: list[int], **cfg) -> None:
    for acc_id in account_ids:
        save_warm(acc_id, **cfg)


def set_warm_running(account_id: int, running: bool) -> None:
    with session_scope() as db:
        w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
        if not w:
            w = WarmConfig(account_id=account_id)
            db.add(w)
        w.is_running = running
        if running:
            w.next_run_at = datetime.now(timezone.utc)
            w.last_error = ""
        acc = db.get(Account, account_id)
        name = acc.name if acc else ""
    notify.log_event("Aquecimento " + ("iniciado" if running else "parado"), "warm", name)


def set_warm_running_many(account_ids: list[int], running: bool) -> int:
    for acc_id in account_ids:
        set_warm_running(acc_id, running)
    return len(account_ids)


def run_warm_once(account_id: int) -> dict:
    """Executa uma sessão de aquecimento agora. Retorna o resumo."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
        if not acc:
            return {"ok": False, "message": "Conta não encontrada"}
        if not w:
            w = WarmConfig(account_id=account_id)
            db.add(w)
            db.flush()
        params = {
            "likes": w.likes_per_run, "stories": w.stories_per_run,
            "follows": w.follows_per_run, "saves": w.saves_per_run,
            "comments": w.comments_per_run or 0, "story_likes": w.story_likes_per_run or 0,
            "unfollows": w.unfollows_per_run or 0, "scrolls": w.scrolls_per_run or 1,
        }
        tags = [t.strip() for t in (w.hashtags or "").split(",") if t.strip()]
        name = acc.name

    try:
        summary, settings = ig.warm_session(acc, hashtags=tags or None, **params)
    except ig.InstagramError as exc:
        with session_scope() as db:
            w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
            if w:
                w.last_error = str(exc)
        metrics.bump("error")
        notify.log_event(f"Falha no aquecimento: {exc}", "error", name)
        return {"ok": False, "message": str(exc)}

    actions = (summary["liked"] + summary["story_viewed"] + summary["story_liked"]
               + summary["commented"] + summary["followed"] + summary["unfollowed"] + summary["saved"])
    text = (f"❤️ {summary['liked']} · 💬 {summary['commented']} · 👁 {summary['story_viewed']} stories · "
            f"💗 {summary['story_liked']} · ➕ {summary['followed']} · ➖ {summary['unfollowed']} · 🔖 {summary['saved']}")
    metrics.bump_many({
        "like": summary["liked"], "comment": summary["commented"], "follow": summary["followed"],
        "unfollow": summary["unfollowed"], "story_view": summary["story_viewed"],
        "story_like": summary["story_liked"], "save": summary["saved"], "scroll": summary["scrolls"],
    })
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if acc:
            acc.session_json = json.dumps(settings)
            _export_session_file(acc.username, settings)
        w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
        if w:
            w.total_actions += actions
            w.last_run_at = datetime.now(timezone.utc)
            w.last_summary = text
            w.last_error = ""
    notify.log_event(f"Aquecimento concluído — {text}", "warm", name)
    return {"ok": True, "summary": summary, "text": text}


def list_warming() -> list[dict]:
    with session_scope() as db:
        rows = db.query(WarmConfig, Account.name).join(Account, WarmConfig.account_id == Account.id).all()
        return [{
            "account_id": w.account_id,
            "account": name,
            "is_running": w.is_running,
            "total_actions": w.total_actions,
            "last_summary": w.last_summary,
        } for w, name in rows]
