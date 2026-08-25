"""Camada de serviço: contas, mídia, publicação e estatísticas.

Cada operação abre sua própria sessão de banco e devolve dados simples (dicts),
para a interface não depender de objetos ORM presos a uma sessão.
"""
import json
import logging
import shutil
import threading
import time
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
from core.loop_timing import jitter_seconds
from core.proxy import normalize_proxy_url, test_proxy as _test_proxy_raw
from core.db import (
    Account,
    Automation,
    AutomationJob,
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
_pending_verify: dict[int, str] = {}

# serializa leitura/gravação do estado do loop (UI + worker na mesma máquina)
_loop_state_lock = threading.RLock()
logger = logging.getLogger(__name__)

RATE_LIMIT_BACKOFF = 600


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        for attempt in range(5):
            try:
                db.commit()
                break
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                if "locked" in str(exc).lower() and attempt < 4:
                    time.sleep(0.15 * (attempt + 1))
                    continue
                raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def setup() -> None:
    init_db()


def resume_after_restart() -> dict:
    """Chamado ao abrir o app: filas no SQLite continuam; redistribui atrasados."""
    from core import automations as auto_svc

    auto = auto_svc.reschedule_overdue_jobs_on_startup(gap_seconds=90)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        sched_due = (
            db.query(ScheduledPost)
            .filter(ScheduledPost.status == "pending", ScheduledPost.scheduled_at <= now)
            .count()
        )
        sched_pending = (
            db.query(ScheduledPost)
            .filter(ScheduledPost.status == "pending")
            .count()
        )
    return {
        **auto,
        "scheduled_due": sched_due,
        "scheduled_pending": sched_pending,
    }


def _export_session_file(username: str, settings: dict) -> None:
    """Salva a sessão em data/sessions/{username}.json e também session.json (última)."""
    try:
        if not username:
            return
        safe = "".join(c for c in username if c.isalnum() or c in "._-") or "conta"
        payload = json.dumps(settings, indent=2, ensure_ascii=False)
        path = SESSIONS_DIR / f"{safe}.json"
        path.write_text(payload, encoding="utf-8")
        # Cópia conveniente com o nome que a galera procura
        (SESSIONS_DIR / "session.json").write_text(payload, encoding="utf-8")
        # Também na pasta do app (instagramm/session.json) — .gitignore já ignora
        from core.config import BASE_DIR

        (BASE_DIR / "session.json").write_text(payload, encoding="utf-8")
        logging.getLogger("service").info("Sessão salva: %s", path)
    except Exception:  # noqa: BLE001
        pass


def _is_session_expired_message(message: str) -> bool:
    low = (message or "").lower()
    return any(x in low for x in (
        "sessão expirada", "loginrequired", "login required", "login_required",
        "refaça o login", "reconecte em contas", "sessão caiu",
    ))


def _is_ban_message(message: str) -> bool:
    low = (message or "").lower()
    return any(x in low for x in (
        "ban", "desativad", "disabled", "suspended", "não encontrado",
        "nao encontrado", "feedback", "restrição", "restricao",
    ))


def _persist_sessionid_from_settings(acc: Account, settings: dict) -> None:
    if acc.sessionid_enc:
        return
    sid = ig._extract_sessionid(settings)
    if sid:
        acc.sessionid_enc = encrypt_secret(sid)


def _mark_session_expired(db, acc: Account, message: str) -> None:
    acc.status = "error"
    acc.status_message = message or "Sessão expirada. Refaça o login em Contas."
    notify.log_event("⚠️ Sessão expirada — faça login novamente em Contas", "warning", acc.name)


def _mark_account_health(db, acc: Account, probe: dict) -> None:
    """Atualiza status da conta a partir do probe (healthy/banned/expired/...)."""
    kind = (probe.get("kind") or probe.get("status") or "error").lower()
    msg = probe.get("message") or ""
    if kind == "healthy":
        acc.status = "healthy"
        acc.status_message = "Conectada"
        if probe.get("settings"):
            acc.session_json = json.dumps(probe["settings"])
            _export_session_file(acc.username, probe["settings"])
        if probe.get("username"):
            acc.username = probe["username"]
        notify.log_event("Conta OK na verificação", "success", acc.name)
        return
    if kind == "banned":
        acc.status = "banned"
        acc.status_message = msg or "Conta banida / desativada"
        notify.log_event(f"🚫 BAN / desativada: {msg}", "error", acc.name)
        return
    if kind == "challenge":
        acc.status = "pending"
        acc.status_message = msg or "Checkpoint do Instagram"
        notify.log_event(f"⚠️ Challenge: {msg}", "warning", acc.name)
        return
    if kind == "expired":
        _mark_session_expired(db, acc, msg)
        return
    acc.status = "error"
    acc.status_message = msg or "Erro na verificação"
    notify.log_event(f"Erro na verificação: {msg}", "error", acc.name)


def recent_events(limit: int = 80) -> list[dict]:
    """Eventos do sistema (conexões, posts, aquecimento, erros)."""
    return notify.recent_events(limit)


# ---------------- Contas ----------------

def _account_dict(acc: Account, db) -> dict:
    from core.device import DEVICE_BY_KEY, device_key_from_settings

    stats = usage_stats(db, acc.id, acc.max_posts_per_day, acc.max_posts_per_hour)
    loop = acc.loop
    dkey = (getattr(acc, "device_key", "") or "").strip()
    if not dkey and acc.session_json:
        try:
            dkey = device_key_from_settings(json.loads(acc.session_json))
        except Exception:  # noqa: BLE001
            dkey = ""
    dlabel = DEVICE_BY_KEY[dkey]["label"] if dkey in DEVICE_BY_KEY else (dkey or "")
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
        "has_sessionid": bool(getattr(acc, "sessionid_enc", "")),
        "device_key": dkey,
        "device_label": dlabel,
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


def test_proxy(raw: str) -> dict:
    """Testa proxy (IP de saída). Usado pelo dialog de Contas."""
    return _test_proxy_raw(raw)


def create_account(
    *,
    name: str,
    username: str = "",
    password: str = "",
    proxy_url: str = "",
    default_caption: str = "",
    max_posts_per_day: int = 0,
    max_posts_per_hour: int = 0,
    device_key: str = "",
) -> int:
    from core.device import AUTO_DEVICE_KEY, DEVICE_BY_KEY

    dkey = (device_key or "").strip()
    if dkey in ("", AUTO_DEVICE_KEY):
        dkey = ""
    elif dkey not in DEVICE_BY_KEY:
        dkey = ""

    with session_scope() as db:
        acc = Account(
            name=name.strip(),
            username=(username or "").strip().lstrip("@").lower(),
            proxy_url=normalize_proxy_url(proxy_url),
            default_caption=default_caption[:INSTAGRAM_CAPTION_MAX],
            max_posts_per_day=max(0, int(max_posts_per_day or 0)),
            max_posts_per_hour=max(0, int(max_posts_per_hour or 0)),
            device_key=dkey,
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
        if "sessionid" in fields:
            sid = fields.pop("sessionid")
            if sid:
                acc.sessionid_enc = encrypt_secret(sid.strip())
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
    _pending_verify.pop(account_id, None)
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)


def save_account_settings(account_id: int, **fields) -> dict:
    """Salva proxy, limites e dados da conta sem tentar reconectar."""
    from core.device import AUTO_DEVICE_KEY, DEVICE_BY_KEY

    if "password" in fields and not fields["password"]:
        fields.pop("password")
    if "sessionid" in fields and not fields["sessionid"]:
        fields.pop("sessionid")
    if "device_key" in fields:
        dkey = (fields.get("device_key") or "").strip()
        if dkey in ("", AUTO_DEVICE_KEY):
            # automático: só limpa se a conta ainda não tem sessão (login novo)
            with session_scope() as db:
                acc = db.get(Account, account_id)
                if acc and (acc.session_json or (getattr(acc, "device_key", "") or "").strip()):
                    fields.pop("device_key", None)
                else:
                    fields["device_key"] = ""
        elif dkey not in DEVICE_BY_KEY:
            fields.pop("device_key", None)
        else:
            # não troca modelo de conta já conectada com sessão
            with session_scope() as db:
                acc = db.get(Account, account_id)
                if acc and acc.session_json and (getattr(acc, "device_key", "") or "").strip():
                    fields.pop("device_key", None)
                else:
                    fields["device_key"] = dkey
    update_account(account_id, **fields)
    return {"ok": True, "message": "Dados da conta salvos (proxy, sessionid, limites, etc.)"}


def retry_after_challenge(account_id: int, challenge_code: str) -> dict:
    """Reenvia login após o usuário digitar o código do challenge (e-mail/SMS)."""
    from core import challenge_flow

    challenge_flow.preset_code(account_id, challenge_code)
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"status": "error", "message": "Conta não encontrada"}
        pwd = decrypt_secret(acc.password_enc) or None
        sid = decrypt_secret(acc.sessionid_enc) if acc.sessionid_enc else None
    verify = _pending_verify.get(account_id)
    if pwd:
        return connect_account(account_id, password=pwd, verification_code=verify)
    if sid:
        return connect_account(account_id, sessionid=sid)
    return {"status": "error", "message": "Informe senha ou sessionid para reconectar."}


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

        sid_input = (sessionid or "").strip()
        if sid_input:
            acc.sessionid_enc = encrypt_secret(sid_input)
            acc.session_json = ""
            db.flush()

        saved_sid = decrypt_secret(acc.sessionid_enc) or None if acc.sessionid_enc else None
        effective_sid = sid_input or saved_sid
        pwd = password or decrypt_secret(acc.password_enc) or None

        from core.device import device_key_from_settings

        # Modelo já atribuído à conta: nunca troca em reconexão
        saved_device_key = (getattr(acc, "device_key", "") or "").strip()
        if not saved_device_key and acc.session_json:
            try:
                saved_device_key = device_key_from_settings(json.loads(acc.session_json))
            except Exception:  # noqa: BLE001
                saved_device_key = ""

        # reaproveita estado da 1ª tentativa quando enviando o código 2FA
        pending_2fa = _pending_2fa.get(account_id)
        settings = None
        if pending_2fa:
            if isinstance(pending_2fa.get("settings"), dict):
                settings = pending_2fa["settings"]
            elif isinstance(pending_2fa, dict) and pending_2fa.get("uuids"):
                settings = pending_2fa
            else:
                settings = pending_2fa
        if not settings and acc.session_json and not sid_input:
            # Só reusa sessão salva em 2FA / check sem senha (não no login senha do zero)
            if verification_code or not pwd:
                try:
                    settings = json.loads(acc.session_json)
                except json.JSONDecodeError:
                    settings = None

        if verification_code:
            _pending_verify[account_id] = verification_code.strip()

        # Login novo (sem settings): usa device já salvo, ou pool escolhe outro modelo
        login_device_key = saved_device_key or None
        acc_username = acc.username
        acc_proxy = acc.proxy_url
        acc_name = acc.name

        try:
            if verification_code and pending_2fa and acc_username and pwd:
                # Caminho rápido: só envia o TOTP, sem refazer login Bloks inteiro
                result = ig.complete_two_factor(
                    username=acc_username,
                    password=pwd,
                    verification_code=verification_code,
                    pending=pending_2fa if isinstance(pending_2fa, dict) else {"settings": pending_2fa},
                    proxy_url=acc_proxy,
                    account_id=account_id,
                    device_key=login_device_key,
                )
            elif effective_sid and not pwd and not verification_code:
                result = ig.login(
                    sessionid=effective_sid, proxy_url=acc_proxy,
                    account_id=account_id, settings=settings,
                    device_key=login_device_key,
                )
            elif acc_username and pwd:
                result = ig.login(
                    username=acc_username,
                    password=pwd,
                    sessionid=sid_input or None,
                    verification_code=verification_code,
                    proxy_url=acc_proxy,
                    settings=settings if not (sid_input) else None,
                    account_id=account_id,
                    device_key=login_device_key,
                )
            elif effective_sid:
                result = ig.login(
                    sessionid=effective_sid, proxy_url=acc_proxy,
                    account_id=account_id, settings=settings,
                    device_key=login_device_key,
                )
            else:
                return {"status": "error", "message": "Informe senha ou sessionid para conectar."}
        except ig.InstagramError as exc:
            if exc.kind == "two_factor":
                payload = getattr(exc, "pending_2fa", None) or (
                    {"settings": exc.settings} if exc.settings else None
                )
                if payload:
                    _pending_2fa[account_id] = payload
                acc.status = "pending"
                acc.status_message = "Aguardando código 2FA"
                return {"status": "needs_2fa", "message": str(exc)}
            if exc.kind == "challenge":
                if exc.settings:
                    _pending_2fa[account_id] = exc.settings
                acc.status = "pending"
                acc.status_message = str(exc)
                return {"status": "needs_challenge", "message": str(exc)}
            if getattr(exc, "kind", "") == "login_required" or _is_session_expired_message(str(exc)):
                _mark_session_expired(db, acc, str(exc))
            else:
                acc.status = "error"
                acc.status_message = str(exc)
            return {"status": "error", "message": str(exc)}

        _pending_2fa.pop(account_id, None)
        _pending_verify.pop(account_id, None)
        acc.session_json = json.dumps(result["settings"])
        _persist_sessionid_from_settings(acc, result["settings"])
        # Grava modelo usado (pool ou inferido da sessão) — fixo daí em diante
        dkey = (result.get("device_key") or "").strip() or device_key_from_settings(result["settings"]) or saved_device_key
        if dkey:
            acc.device_key = dkey
        acc.username = result.get("username") or acc.username
        acc.status = "healthy"
        acc.status_message = "Conectada"
        _export_session_file(acc.username, result["settings"])
        notify.log_event("Conta conectada", "success", acc.name)
        return {"status": "connected", "message": "Conta conectada com sucesso"}


def check_account(account_id: int) -> dict:
    """Verifica se a conta está OK, caiu (sessão) ou tomou ban."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"status": "error", "kind": "error", "message": "Conta não encontrada"}
        try:
            probe = ig.probe_account_health(acc)
        except Exception as exc:  # noqa: BLE001
            probe = {"status": "error", "kind": "error", "message": str(exc)}

        _mark_account_health(db, acc, probe)
        from core.device import device_key_from_settings

        if probe.get("settings"):
            dkey = device_key_from_settings(probe["settings"])
            if dkey and not (getattr(acc, "device_key", "") or "").strip():
                acc.device_key = dkey

        return {
            "id": acc.id,
            "name": acc.name,
            "username": acc.username or probe.get("username") or "",
            "status": acc.status,
            "kind": probe.get("kind") or acc.status,
            "message": acc.status_message or probe.get("message") or "",
            "ok": (probe.get("kind") == "healthy"),
        }


def check_all_accounts() -> dict:
    """Verifica todas as contas com sessão. Retorna resumo + listas por tipo."""
    results: list[dict] = []
    banned: list[dict] = []
    expired: list[dict] = []
    challenge: list[dict] = []
    errors: list[dict] = []
    healthy = 0

    with session_scope() as db:
        accounts = db.query(Account).filter(Account.session_json != "").all()
        ids = [a.id for a in accounts]

    for acc_id in ids:
        row = check_account(acc_id)
        results.append(row)
        kind = (row.get("kind") or row.get("status") or "").lower()
        if kind == "healthy" or row.get("status") == "healthy":
            healthy += 1
        elif kind == "banned" or row.get("status") == "banned":
            banned.append(row)
        elif kind == "expired":
            expired.append(row)
        elif kind == "challenge" or row.get("status") == "pending":
            challenge.append(row)
        else:
            errors.append(row)
        # pausa leve entre contas
        time.sleep(1.2)

    return {
        "total": len(results),
        "healthy": healthy,
        "banned": banned,
        "expired": expired,
        "challenge": challenge,
        "errors": errors,
        "results": results,
        # compat com app antigo (toast de sessão)
        "expired_compat": [
            {"id": e["id"], "name": e.get("name") or "", "username": e.get("username") or ""}
            for e in expired
        ],
    }


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


def update_account_profile(
    account_id: int,
    *,
    biography: str | None = None,
    picture_path: str | None = None,
) -> dict:
    """Atualiza bio e/ou foto de perfil de uma conta conectada."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"ok": False, "message": "Conta não encontrada"}
        if not acc.session_json or acc.status != "healthy":
            return {"ok": False, "message": "Conta precisa estar conectada (sessão válida)"}
        try:
            local_pic = None
            if picture_path:
                src = Path(picture_path)
                if src.exists() and src.resolve().parent == IMAGES_DIR.resolve():
                    local_pic = str(src)
                else:
                    local_pic = import_image(picture_path)

            result = ig.update_profile(
                acc,
                biography=biography,
                picture_path=local_pic,
            )
            if result.get("settings"):
                acc.session_json = json.dumps(result["settings"])
                _export_session_file(acc.username, result["settings"])
            parts = result.get("changed") or []
            msg = "Perfil atualizado: " + " + ".join(parts) if parts else "Perfil atualizado"
            notify.log_event(msg, "success", acc.name)
            return {"ok": True, "message": msg, "changed": parts}
        except ig.InstagramError as exc:
            msg = str(exc)
            if _is_session_expired_message(msg) or getattr(exc, "kind", "") == "login_required":
                _mark_session_expired(db, acc, msg)
            else:
                notify.log_event(f"Falha ao editar perfil: {msg}", "error", acc.name)
            return {"ok": False, "message": msg}


def bulk_update_profiles(
    account_ids: list[int],
    *,
    picture_paths: list[str] | None = None,
    biography: str | None = None,
    biographies: list[str] | None = None,
) -> dict:
    """Aplica foto/bio em várias contas.

    - Fotos: 1ª conta ← 1ª foto, 2ª ← 2ª… se houver menos fotos, repete em ciclo.
    - Bio única (`biography`) para todas, OU lista `biographies` na ordem das contas.
    """
    ids = [int(x) for x in (account_ids or [])]
    if not ids:
        return {"ok": False, "message": "Selecione pelo menos uma conta", "results": []}

    pics = [p for p in (picture_paths or []) if p and Path(p).exists()]
    bios_list = [str(b).strip() for b in (biographies or []) if str(b).strip()]
    shared_bio = None if biography is None else str(biography).strip()

    if not pics and shared_bio is None and not bios_list:
        return {"ok": False, "message": "Informe fotos e/ou bio", "results": []}

    results = []
    ok_n = 0
    for i, acc_id in enumerate(ids):
        pic = pics[i % len(pics)] if pics else None
        if bios_list:
            bio = bios_list[i] if i < len(bios_list) else bios_list[-1]
        else:
            bio = shared_bio
        # Se só tem fotos sem bio, biography=None; se só bio, picture=None
        res = update_account_profile(
            acc_id,
            biography=bio,
            picture_path=pic,
        )
        results.append({"account_id": acc_id, **res})
        if res.get("ok"):
            ok_n += 1
        # leve pausa entre contas (anti-spam)
        if i < len(ids) - 1:
            time.sleep(2.5)

    return {
        "ok": ok_n > 0,
        "message": f"{ok_n}/{len(ids)} conta(s) atualizada(s)",
        "ok_count": ok_n,
        "total": len(ids),
        "results": results,
    }


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
            acc.status = "healthy"
            acc.status_message = "Conectada"
            _persist_sessionid_from_settings(acc, result["settings"])
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
            if getattr(exc, "kind", "") == "login_required" or _is_session_expired_message(str(exc)):
                _mark_session_expired(db, acc, str(exc))
            else:
                acc.status_message = str(exc)
            metrics.bump("error")
            notify.log_event(f"Falha ao publicar Reel: {exc}", "error", acc.name)
            return {"ok": False, "message": str(exc), "kind": exc.kind}


def post_story_now(
    account_id: int,
    media_path: str,
    caption: str = "",
    link: str | dict | None = None,
) -> dict:
    """Publica um Story (foto ou vídeo) imediatamente e registra no log."""
    with session_scope() as db:
        acc = db.get(Account, account_id)
        if not acc:
            return {"ok": False, "message": "Conta não encontrada"}
        final_caption = caption or ""
        link_url = link.get("url") if isinstance(link, dict) else (link or "")
        try:
            result = ig.post_story(acc, media_path, final_caption, link)
            acc.session_json = json.dumps(result["settings"])
            acc.status = "healthy"
            acc.status_message = "Conectada"
            _persist_sessionid_from_settings(acc, result["settings"])
            _export_session_file(acc.username, result["settings"])
            db.add(PostLog(
                account_id=acc.id,
                media_id=result["media_pk"],
                media_type="story",
                caption_preview=final_caption[:300],
                video_path=media_path,
                status="success",
            ))
            kind = "vídeo" if result.get("kind") == "video" else "foto"
            metrics.bump("post")
            link_txt = f" 🔗 {link_url}" if link_url else ""
            notify.log_event(f"Story publicado ({kind}) 📸{link_txt}", "success", acc.name)
            return {"ok": True, "media_pk": result["media_pk"], "kind": result.get("kind", "")}
        except ig.InstagramError as exc:
            db.add(PostLog(
                account_id=acc.id,
                media_type="story",
                video_path=media_path,
                status="error",
                error_message=str(exc),
            ))
            acc.status = "error" if exc.kind != "rate_limit" else acc.status
            if getattr(exc, "kind", "") == "login_required" or _is_session_expired_message(str(exc)):
                _mark_session_expired(db, acc, str(exc))
            else:
                acc.status_message = str(exc)
            metrics.bump("error")
            notify.log_event(f"Falha ao publicar Story: {exc}", "error", acc.name)
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

def _loop_video_paths(videos_json: str) -> list[str]:
    try:
        return [str(v.get("video_path", "")) for v in json.loads(videos_json or "[]")]
    except Exception:  # noqa: BLE001
        return []


def _canonical_videos_json(videos: list[dict]) -> str:
    items = [
        {
            "video_path": str(v.get("video_path", "")),
            "cover_path": str(v.get("cover_path", "") or ""),
            "caption": str(v.get("caption", "") or ""),
        }
        for v in videos
    ]
    return json.dumps(items, sort_keys=True, ensure_ascii=False)


def list_due_loop_account_ids() -> list[int]:
    """Contas com loop rodando e horário de postagem vencido."""
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        rows = db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).all()
        due: list[int] = []
        for loop in rows:
            nxt = loop.next_run_at
            if nxt and nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            if nxt and nxt > now:
                continue
            due.append(loop.account_id)
        return due


def prepare_loop_post(account_id: int) -> tuple[dict | None, bool]:
    """Reserva o slot ANTES do upload. Retorna (claim, houve_alteração_no_banco)."""
    now = datetime.now(timezone.utc)
    with _loop_state_lock:
        with session_scope() as db:
            loop = db.query(LoopConfig).filter(
                LoopConfig.account_id == account_id,
                LoopConfig.is_running.is_(True),
            ).first()
            if not loop:
                return None, False

            nxt = loop.next_run_at
            if nxt and nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            if nxt and nxt > now:
                return None, False

            videos = json.loads(loop.videos_json or "[]")
            if not videos:
                loop.is_running = False
                loop.last_error = "Sem vídeos na lista"
                return None, True

            acc = db.get(Account, account_id)
            if not acc or not acc.is_active:
                return None, False

            stats = usage_stats(db, account_id, acc.max_posts_per_day, acc.max_posts_per_hour)
            if stats["blocked_hour"]:
                loop.next_run_at = now + timedelta(seconds=jitter_seconds(120))
                loop.last_error = "Limite por hora atingido"
                return None, True
            if stats["blocked_day"]:
                loop.next_run_at = now + timedelta(seconds=jitter_seconds(120))
                loop.last_error = "Limite diário atingido"
                return None, True

            recorrente = (loop.mode or "continuo") == "recorrente"
            if recorrente and (loop.batch_remaining or 0) <= 0:
                loop.batch_remaining = max(1, loop.batch_size or 1)

            idx = loop.current_index % len(videos)
            item = videos[idx]

            hold = max(int(loop.interval_seconds or 120), 90)
            loop.next_run_at = now + timedelta(seconds=hold)

            claim = {
                "account_id": account_id,
                "idx": idx,
                "video_path": item.get("video_path", ""),
                "caption": item.get("caption") or loop.caption,
                "cover_path": item.get("cover_path") or "",
                "recorrente": recorrente,
                "interval_seconds": loop.interval_seconds,
                "batch_interval_minutes": loop.batch_interval_minutes,
                "batch_remaining": loop.batch_remaining,
                "video_count": len(videos),
            }
            return claim, True


def finalize_loop_post(account_id: int, claim: dict, result: dict) -> bool:
    """Atualiza índice e próximo horário depois do upload."""
    now = datetime.now(timezone.utc)
    with _loop_state_lock:
        with session_scope() as db:
            loop = db.query(LoopConfig).filter(
                LoopConfig.account_id == account_id,
                LoopConfig.is_running.is_(True),
            ).first()
            if not loop:
                return True

            acc = db.get(Account, account_id)
            recorrente = claim["recorrente"]
            idx = claim["idx"]
            count = claim["video_count"]

            if result.get("ok"):
                loop.total_posts += 1
                loop.last_error = ""
                if recorrente:
                    loop.current_index = (idx + 1) % count
                    loop.batch_remaining = max(0, (claim["batch_remaining"] or 1) - 1)
                    if loop.batch_remaining > 0:
                        loop.next_run_at = now + timedelta(seconds=jitter_seconds(loop.interval_seconds))
                    else:
                        base = (loop.batch_interval_minutes or 360) * 60
                        loop.next_run_at = now + timedelta(seconds=jitter_seconds(base))
                else:
                    next_index = idx + 1
                    if next_index >= count:
                        loop.is_running = False
                        loop.current_index = 0
                        loop.next_run_at = None
                        try:
                            notify.log_event(
                                f"Loop contínuo concluído: {count} vídeo(s) publicado(s). Parado automaticamente.",
                                level="success",
                                account=acc.username if acc else "",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        loop.current_index = next_index
                        loop.next_run_at = now + timedelta(seconds=jitter_seconds(loop.interval_seconds))
            else:
                loop.last_error = result.get("message", "Erro")
                backoff = RATE_LIMIT_BACKOFF if result.get("kind") == "rate_limit" else loop.interval_seconds
                loop.next_run_at = now + timedelta(seconds=max(30, int(backoff or 120)))
            return True


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
    with _loop_state_lock:
        with session_scope() as db:
            loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
            if not loop:
                loop = LoopConfig(account_id=account_id)
                db.add(loop)
            new_videos = _canonical_videos_json(videos)
            old_paths = _loop_video_paths(loop.videos_json)
            new_paths = _loop_video_paths(new_videos)
            # só zera o índice se a lista de vídeos mudou (não por capa/legenda/ordem JSON)
            if old_paths != new_paths:
                loop.current_index = 0
            elif loop.is_running and new_paths and loop.current_index >= len(new_paths):
                loop.current_index = 0
            loop.videos_json = new_videos
            loop.interval_seconds = max(30, int(interval_seconds))
            loop.caption = caption
            loop.mode = mode if mode in ("continuo", "recorrente") else "continuo"
            loop.batch_size = max(1, int(batch_size or 1))
            loop.batch_interval_minutes = max(5, int(batch_interval_minutes or 5))


def set_loop_running(account_id: int, running: bool) -> None:
    with _loop_state_lock:
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
            else:
                loop.next_run_at = None
            acc = db.get(Account, account_id)
            name = acc.name if acc else ""
            mode = loop.mode or "continuo"
    label = "Loop recorrente" if mode == "recorrente" else "Loop contínuo"
    notify.log_event(label + (" iniciado" if running else " parado"), "info", name)


def count_running_loops() -> int:
    with session_scope() as db:
        return db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).count()


def stop_all_loops() -> int:
    """Para todos os loops ativos. Retorna quantos foram parados."""
    stopped = 0
    with _loop_state_lock:
        with session_scope() as db:
            loops = db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).all()
            for loop in loops:
                loop.is_running = False
                loop.next_run_at = None
                stopped += 1
    if stopped:
        notify.log_event(f"{stopped} loop(s) parado(s)", "info")
    return stopped


# ---------------- Agendamentos ----------------

def add_scheduled(
    account_id: int,
    video_path: str,
    scheduled_at: datetime,
    caption: str = "",
    cover_path: str = "",
    *,
    post_type: str = "reel",
    link_url: str = "",
    link_text: str = "",
    link_x: float = 0.5,
    link_y: float = 0.8,
    link_w: float = 0.6,
    link_h: float = 0.068625,
) -> None:
    with session_scope() as db:
        db.add(ScheduledPost(
            account_id=account_id,
            post_type=post_type or "reel",
            video_path=video_path,
            cover_path=cover_path or "",
            caption=caption,
            link_url=link_url or "",
            link_text=link_text or "",
            link_x=float(link_x),
            link_y=float(link_y),
            link_w=float(link_w),
            link_h=float(link_h),
            scheduled_at=scheduled_at,
            status="pending",
        ))


def schedule_stories(
    account_ids: list[int],
    media_paths: list[str],
    schedule_times: list[datetime],
    *,
    caption: str = "",
    link_url: str = "",
    link_text: str = "",
    link_x: float = 0.5,
    link_y: float = 0.8,
    link_w: float = 0.6,
    link_h: float = 0.068625,
) -> dict:
    """Agenda stories: cada mídia × horário × conta."""
    if not account_ids:
        return {"ok": False, "message": "Selecione pelo menos uma conta"}
    if not media_paths:
        return {"ok": False, "message": "Selecione pelo menos uma mídia"}
    if not schedule_times:
        return {"ok": False, "message": "Adicione pelo menos um horário"}

    imported = [import_media_for_story(p) for p in media_paths if Path(p).exists()]
    if not imported:
        return {"ok": False, "message": "Nenhuma mídia válida"}

    created = 0
    with session_scope() as db:
        healthy = {
            a.id for a in db.query(Account).filter(
                Account.id.in_(account_ids),
                Account.status == "healthy",
                Account.is_active.is_(True),
            ).all()
        }
        if not healthy:
            return {"ok": False, "message": "Nenhuma conta saudável selecionada"}

        for acc_id in account_ids:
            if acc_id not in healthy:
                continue
            for local in imported:
                for when in schedule_times:
                    db.add(ScheduledPost(
                        account_id=acc_id,
                        post_type="story",
                        video_path=local,
                        caption=caption or "",
                        link_url=link_url or "",
                        link_text=link_text or "",
                        link_x=float(link_x),
                        link_y=float(link_y),
                        link_w=float(link_w),
                        link_h=float(link_h),
                        scheduled_at=when,
                        status="pending",
                    ))
                    created += 1
    notify.log_event(f"{created} story(s) agendado(s)", "success")
    return {"ok": True, "message": f"{created} publicação(ões) agendada(s)", "count": created}


def import_media_for_story(src: str) -> str:
    ext = Path(src).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return import_image(src)
    return import_video(src)


def publish_stories_now(
    account_ids: list[int],
    media_paths: list[str],
    *,
    caption: str = "",
    link_url: str = "",
    link_text: str = "",
    link_x: float = 0.5,
    link_y: float = 0.8,
    link_w: float = 0.6,
    link_h: float = 0.068625,
) -> dict:
    if not account_ids or not media_paths:
        return {"ok": False, "message": "Contas e mídias obrigatórias"}
    link = None
    if link_url:
        link = {
            "url": link_url,
            "text": link_text,
            "x": link_x,
            "y": link_y,
            "width": link_w,
            "height": link_h,
        }
    ok_count = 0
    errors: list[str] = []
    for acc_id in account_ids:
        for media in media_paths:
            res = post_story_now(acc_id, media, caption, link)
            if res.get("ok"):
                ok_count += 1
            else:
                errors.append(res.get("message") or "Erro")
    if ok_count == 0:
        return {"ok": False, "message": errors[0] if errors else "Falha ao publicar"}
    return {"ok": True, "message": f"{ok_count} story(s) publicado(s)", "errors": errors}


def list_scheduled(post_type: str | None = None) -> list[dict]:
    with session_scope() as db:
        q = (
            db.query(ScheduledPost, Account.name)
            .join(Account, ScheduledPost.account_id == Account.id)
        )
        if post_type:
            q = q.filter(ScheduledPost.post_type == post_type)
        rows = q.order_by(ScheduledPost.scheduled_at).all()
        return [{
            "id": s.id,
            "account": name,
            "post_type": getattr(s, "post_type", None) or "reel",
            "video_name": Path(s.video_path).name if s.video_path else "",
            "caption": s.caption,
            "link_url": getattr(s, "link_url", "") or "",
            "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else "",
            "status": s.status,
            "error": s.error_message,
        } for s, name in rows]


def process_scheduled_post(post_id: int) -> bool:
    """Publica um agendamento due."""
    db = SessionLocal()
    try:
        post = db.get(ScheduledPost, post_id)
        if not post or post.status != "pending":
            return False
        acc_id = post.account_id
        post_type = getattr(post, "post_type", None) or "reel"
        media = post.video_path
        caption = post.caption or ""
        cover = post.cover_path or None
        link = None
        if getattr(post, "link_url", ""):
            link = {
                "url": post.link_url,
                "text": getattr(post, "link_text", "") or "",
                "x": float(getattr(post, "link_x", 0.5) or 0.5),
                "y": float(getattr(post, "link_y", 0.8) or 0.8),
                "width": float(getattr(post, "link_w", 0.6) or 0.6),
                "height": float(getattr(post, "link_h", 0.068625) or 0.068625),
            }
    finally:
        db.close()

    if post_type == "story":
        result = post_story_now(acc_id, media, caption, link)
    else:
        result = post_reel_now(acc_id, media, caption, cover)

    db = SessionLocal()
    try:
        post = db.get(ScheduledPost, post_id)
        if not post:
            return True
        if result.get("ok"):
            post.status = "posted"
        else:
            post.status = "error"
            post.error_message = result.get("message", "Erro")
        db.commit()
    finally:
        db.close()
    return True


def list_due_scheduled_ids(limit: int = 5) -> list[int]:
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        rows = (
            db.query(ScheduledPost.id)
            .filter(ScheduledPost.status == "pending", ScheduledPost.scheduled_at <= now)
            .order_by(ScheduledPost.scheduled_at)
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]
    finally:
        db.close()


def cancel_scheduled(post_id: int) -> None:
    with session_scope() as db:
        post = db.get(ScheduledPost, post_id)
        if post and post.status == "pending":
            post.status = "cancelled"


def dashboard_stats() -> dict:
    with session_scope() as db:
        total = db.query(Account).count()
        connected = db.query(Account).filter(Account.status == "healthy").count()
        autos = db.query(Automation).filter(Automation.status == "active").count()
        jobs_pending = db.query(AutomationJob).filter(AutomationJob.status == "pending").count()
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        posts_ok = db.query(PostLog).filter(PostLog.status == "success", PostLog.posted_at >= day_ago).count()
        posts_fail = db.query(PostLog).filter(PostLog.status != "success", PostLog.posted_at >= day_ago).count()
        attempts = posts_ok + posts_fail
        success_rate = (posts_ok / attempts * 100.0) if attempts else 0.0
        pending = db.query(ScheduledPost).filter(ScheduledPost.status == "pending").count()
        return {
            "accounts": total,
            "connected": connected,
            "automations_active": autos,
            "jobs_pending": jobs_pending,
            "posts_24h": posts_ok,
            "posts_today": posts_ok,
            "success_rate": round(success_rate, 1),
            "scheduled_pending": pending,
            "loops_running": autos,
            "warming": jobs_pending,
        }


def list_running_tasks() -> list[dict]:
    """Lista automações ativas (Instablack local)."""
    items: list[dict] = []
    with session_scope() as db:
        autos = (
            db.query(Automation)
            .filter(Automation.status == "active")
            .order_by(Automation.id.desc())
            .all()
        )
        for a in autos:
            pending = db.query(AutomationJob).filter(
                AutomationJob.automation_id == a.id,
                AutomationJob.status == "pending",
            ).count()
            posted = db.query(AutomationJob).filter(
                AutomationJob.automation_id == a.id,
                AutomationJob.status == "posted",
            ).count()
            detail = f"{posted} ok · {pending} na fila"
            if a.last_error:
                detail = (a.last_error or "")[:80]
            items.append({
                "type": "automation",
                "automation_id": a.id,
                "account_id": None,
                "name": a.name,
                "username": "",
                "title": a.name or f"Automação #{a.id}",
                "activity": f"Reels a cada {a.interval_minutes} min",
                "detail": detail,
                "icon": "⚡",
            })
    return items


def list_running_tasks_legacy() -> list[dict]:
    """Legado: loops/warm/stagger — mantido só se precisar depurar."""
    items: list[dict] = []
    with session_scope() as db:
        loops = (
            db.query(LoopConfig, Account)
            .join(Account, LoopConfig.account_id == Account.id)
            .filter(LoopConfig.is_running.is_(True))
            .order_by(Account.name)
            .all()
        )
        for loop, acc in loops:
            mode = "recorrente" if loop.mode == "recorrente" else "contínuo"
            posts = loop.total_posts or 0
            detail = f"{posts} publicação(ões)" if posts else "iniciando"
            if loop.last_error:
                detail = loop.last_error[:80]
            items.append({
                "type": "loop",
                "account_id": acc.id,
                "name": acc.name,
                "username": acc.username,
                "title": f"{acc.name} (@{acc.username})",
                "activity": f"Loop {mode}",
                "detail": detail,
                "icon": "🔁",
            })

        warms = (
            db.query(WarmConfig, Account)
            .join(Account, WarmConfig.account_id == Account.id)
            .filter(WarmConfig.is_running.is_(True))
            .order_by(Account.name)
            .all()
        )
        for warm, acc in warms:
            detail = (warm.last_summary or "aquecendo").strip()[:80]
            items.append({
                "type": "warm",
                "account_id": acc.id,
                "name": acc.name,
                "username": acc.username,
                "title": f"{acc.name} (@{acc.username})",
                "activity": "Aquecendo conta",
                "detail": detail,
                "icon": "🔥",
            })

        stagger = (
            db.query(StaggerItem, Account)
            .join(Account, StaggerItem.account_id == Account.id)
            .filter(StaggerItem.status == "pending")
            .order_by(StaggerItem.activate_at)
            .all()
        )
        for item, acc in stagger:
            when = item.activate_at.strftime("%H:%M") if item.activate_at else "—"
            items.append({
                "type": "stagger",
                "account_id": acc.id,
                "name": acc.name,
                "username": acc.username,
                "title": f"{acc.name} (@{acc.username})",
                "activity": "Fila escalonada",
                "detail": f"ativa às {when}",
                "icon": "⚡",
            })
    return items


# ---------------- Gráficos / métricas ----------------

WARM_KEYS = ["like", "comment", "follow", "unfollow", "story_view", "story_like", "save", "scroll"]


def chart_data(days: int = 7) -> dict:
    """Dados agregados para os gráficos do dashboard."""
    posts = metrics.series("post", days, weekday=(days <= 7))
    warm = metrics.series_sum(WARM_KEYS, days)
    errors = metrics.series("error", days, weekday=(days <= 7))
    breakdown = metrics.totals(WARM_KEYS, days)
    return {
        "posts": posts,
        "warm": warm,
        "errors": errors,
        "breakdown": breakdown,
        "days": days,
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
