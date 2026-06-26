import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("meta_throttle")

_lock = threading.Lock()
_last_publish_at: float | None = None
_cooldown_until: float | None = None
_cooldown_until_wall: datetime | None = None
_last_publish_wall: datetime | None = None

# Intervalo mínimo entre publicações de qualquer conta (protege limite do app Meta).
PUBLISH_GAP_SECONDS = max(30, int(os.getenv("META_PUBLISH_GAP_SECONDS", "120")))
# Pausa global após erro (#4) Application request limit reached.
APP_COOLDOWN_SECONDS = max(300, int(os.getenv("META_APP_COOLDOWN_SECONDS", "3600")))


def _now() -> float:
    return time.monotonic()


def report_app_rate_limit() -> None:
    global _cooldown_until, _cooldown_until_wall
    with _lock:
        _cooldown_until = _now() + APP_COOLDOWN_SECONDS
        _cooldown_until_wall = datetime.now(timezone.utc) + timedelta(seconds=APP_COOLDOWN_SECONDS)
        logger.warning(
            "Limite da aplicação Meta atingido — pausa global de %ss",
            APP_COOLDOWN_SECONDS,
        )


def mark_publish_complete() -> None:
    global _last_publish_at, _last_publish_wall
    with _lock:
        _last_publish_at = _now()
        _last_publish_wall = datetime.now(timezone.utc)


def check_publish_allowed() -> tuple[bool, str, int | None]:
    """Retorna (permitido, motivo, segundos_restantes)."""
    now = _now()
    with _lock:
        if _cooldown_until and now < _cooldown_until:
            left = int(_cooldown_until - now) + 1
            mins = max(1, left // 60)
            return (
                False,
                f"Limite da API Meta (app) — aguardando {mins} min antes de novas publicações",
                left,
            )

        if _last_publish_at is not None:
            elapsed = now - _last_publish_at
            if elapsed < PUBLISH_GAP_SECONDS:
                left = int(PUBLISH_GAP_SECONDS - elapsed) + 1
                return (
                    False,
                    f"Fila global — próxima publicação em ~{left}s (evita erro #4 da Meta)",
                    left,
                )

    return True, "", None


def wait_for_publish_slot(timeout: float = 300) -> tuple[bool, str]:
    deadline = _now() + timeout
    reason = "Timeout na fila global"
    while _now() < deadline:
        allowed, reason, _ = check_publish_allowed()
        if allowed:
            return True, ""
        time.sleep(min(5, max(1, deadline - _now())))
    return False, reason


def get_status() -> dict:
    allowed, reason, wait_seconds = check_publish_allowed()
    with _lock:
        cooldown_until = _cooldown_until_wall
        last_publish = _last_publish_wall
    return {
        "publish_allowed": allowed,
        "wait_reason": reason,
        "wait_seconds": wait_seconds,
        "publish_gap_seconds": PUBLISH_GAP_SECONDS,
        "cooldown_seconds": APP_COOLDOWN_SECONDS,
        "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
        "last_publish_at": last_publish.isoformat() if last_publish else None,
    }


def is_app_rate_limit_error(exc: Exception) -> bool:
    # instagrapi: nomes de exceção indicam throttle/limite
    name = exc.__class__.__name__
    if name in ("PleaseWaitFewMinutes", "ClientThrottledError", "RateLimitError"):
        return True
    payload = getattr(exc, "payload", None) or {}
    if isinstance(payload, dict):
        if payload.get("ig_exc") in ("PleaseWaitFewMinutes", "ClientThrottledError", "RateLimitError"):
            return True
        error = payload.get("error", payload)
        if isinstance(error, dict):
            code = error.get("code")
            if code == 4 or str(code) == "4":
                return True
    msg = str(exc).lower()
    return (
        "application request limit" in msg
        or "(#4)" in msg
        or "wait a few minutes" in msg
        or "please wait" in msg
        or "rate limit" in msg
    )
