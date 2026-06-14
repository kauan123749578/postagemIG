import logging

from sqlalchemy.orm import Session

from app.models import Account, PostLog
from app.services.health import check_account_health
from app.services.instagram import INSTAGRAM_CAPTION_MAX, InstagramAPIError, client_from_account
from app.services.rate_limit import can_post

logger = logging.getLogger("publisher")


def _log_post(
    db: Session,
    account_id: int,
    *,
    media_type: str,
    status: str,
    media_id: str = "",
    caption: str = "",
    error_message: str = "",
    used_fallback: bool = False,
) -> PostLog:
    preview = caption[:200] if caption else ""
    if used_fallback:
        preview = f"[Contingência] {preview}"[:200]
    log = PostLog(
        account_id=account_id,
        media_id=media_id,
        media_type=media_type,
        caption_preview=preview,
        status=status,
        error_message=error_message,
    )
    db.add(log)
    return log


def get_active_account(db: Session, account: Account) -> Account:
    if account.is_active and account.health_status != "error":
        return account
    if account.fallback_account_id:
        fallback = db.get(Account, account.fallback_account_id)
        if fallback and fallback.is_active:
            return fallback
    return account


def resolve_post_accounts(db: Session, account: Account) -> tuple[Account, Account | None]:
    primary = account
    fallback = None
    if account.fallback_account_id:
        fallback = db.get(Account, account.fallback_account_id)
    if not primary.is_active or primary.health_status == "error":
        if fallback and fallback.is_active:
            return fallback, primary
    return primary, fallback


def publish_reel(
    db: Session,
    account: Account,
    video_url: str,
    caption: str = "",
    cover_url: str | None = None,
    audio_name: str | None = None,
) -> dict:
    primary, fallback = resolve_post_accounts(db, account)
    caption = (caption or account.default_caption or "")[:INSTAGRAM_CAPTION_MAX]

    for target, is_fallback in ((primary, False), (fallback, True)):
        if not target:
            continue
        allowed, reason = can_post(db, target.id, target.max_posts_per_day, target.max_posts_per_hour)
        if not allowed:
            if is_fallback:
                raise InstagramAPIError(reason)
            continue

        try:
            media_id = client_from_account(target).post_reel(
                video_url, caption, cover_url=cover_url, audio_name=audio_name
            )
            _log_post(
                db, target.id,
                media_type="reel", status="success", media_id=media_id,
                caption=caption, used_fallback=is_fallback,
            )
            db.commit()
            return {"media_id": media_id, "account_id": target.id, "used_fallback": is_fallback}
        except InstagramAPIError as exc:
            _log_post(
                db, target.id,
                media_type="reel", status="error",
                caption=caption, error_message=str(exc), used_fallback=is_fallback,
            )
            check_account_health(db, target)
            if target.health_status == "error" and not is_fallback:
                target.is_active = False
            db.commit()
            if is_fallback or not fallback:
                raise
            logger.warning("Conta %s falhou, tentando contingência %s", primary.name, fallback.name)

    raise InstagramAPIError("Nenhuma conta disponível para publicar")
