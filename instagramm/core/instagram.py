"""Wrapper da instagrapi: login (usuário/senha + 2FA, ou sessionid), sessão e upload local."""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("instagram")


class InstagramError(Exception):
    def __init__(self, message: str, kind: str = "error", settings: dict | None = None):
        super().__init__(message)
        self.kind = kind  # error / two_factor / challenge / rate_limit
        self.settings = settings  # device/uuids para reaproveitar no envio do 2FA


def _friendly(exc: Exception) -> str:
    name = exc.__class__.__name__
    hints = {
        "BadPassword": "Usuário ou senha inválidos.",
        "TwoFactorRequired": "Conta com verificação em duas etapas (2FA).",
        "ChallengeRequired": "O Instagram pediu verificação extra. Tente login por sessionid.",
        "PleaseWaitFewMinutes": "Muitas tentativas. Aguarde alguns minutos.",
        "LoginRequired": "Sessão expirada. Refaça o login.",
        "ClientThrottledError": "Limite do Instagram atingido. Aguarde antes de postar.",
        "ProxyAddressIsBlocked": "Proxy bloqueado pelo Instagram.",
    }
    return hints.get(name, str(exc) or name)


def build_client(proxy_url: str | None = None, settings: dict | None = None):
    from instagrapi import Client

    cl = Client()
    cl.delay_range = [2, 5]
    if settings:
        try:
            cl.set_settings(settings)
        except Exception:  # noqa: BLE001
            logger.warning("Não foi possível carregar settings de sessão")
    if proxy_url and proxy_url.strip():
        try:
            cl.set_proxy(proxy_url.strip())
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(f"Proxy inválido: {exc}") from exc
    return cl


def login(
    *,
    username: str | None = None,
    password: str | None = None,
    sessionid: str | None = None,
    verification_code: str | None = None,
    proxy_url: str | None = None,
    settings: dict | None = None,
) -> dict[str, Any]:
    """Loga e retorna {settings, username, full_name, ...}. Levanta InstagramError."""
    from instagrapi.exceptions import (
        ChallengeRequired,
        TwoFactorRequired,
    )

    cl = build_client(proxy_url, settings)

    try:
        if sessionid and sessionid.strip():
            cl.login_by_sessionid(sessionid.strip())
        elif username and password:
            code = (verification_code or "").strip()
            if code:
                cl.login(username, password, verification_code=code)
            else:
                cl.login(username, password)
        else:
            raise InstagramError("Informe usuário e senha (ou um sessionid).")
    except TwoFactorRequired as exc:
        raise InstagramError(_friendly(exc), kind="two_factor", settings=cl.get_settings()) from exc
    except ChallengeRequired as exc:
        raise InstagramError(_friendly(exc), kind="challenge") from exc
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InstagramError(_friendly(exc)) from exc

    try:
        info = cl.account_info()
    except Exception as exc:  # noqa: BLE001
        raise InstagramError(_friendly(exc)) from exc

    return {
        "settings": cl.get_settings(),
        "username": info.username,
        "full_name": getattr(info, "full_name", ""),
        "follower_count": getattr(info, "follower_count", 0),
        "media_count": getattr(info, "media_count", 0),
    }


def _client_from_account(account, settings: dict):
    cl = build_client(account.proxy_url, settings)
    return cl


def verify_session(account) -> dict[str, Any]:
    """Confere se a sessão salva ainda é válida."""
    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte novamente.")
    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)
    try:
        info = cl.account_info()
    except Exception as exc:  # noqa: BLE001
        raise InstagramError(_friendly(exc)) from exc
    return {
        "settings": cl.get_settings(),
        "username": info.username,
        "follower_count": getattr(info, "follower_count", 0),
        "media_count": getattr(info, "media_count", 0),
    }


def post_reel(account, video_path: str, caption: str = "", cover_path: str | None = None) -> dict[str, Any]:
    """Publica um Reel usando a sessão salva da conta. Retorna {media_pk, code, settings}."""
    from instagrapi.exceptions import LoginRequired

    video = Path(video_path)
    if not video.exists():
        raise InstagramError(f"Vídeo não encontrado: {video_path}")
    thumb = Path(cover_path) if cover_path and Path(cover_path).exists() else None

    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte a conta antes de postar.")

    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)

    def _do():
        kwargs = {}
        if thumb:
            kwargs["thumbnail"] = thumb
        return cl.clip_upload(video, caption or "", **kwargs)

    try:
        media = _do()
    except LoginRequired:
        # tenta re-login automático com a senha salva
        from core.crypto import decrypt_secret

        pwd = decrypt_secret(account.password_enc)
        if not (account.username and pwd):
            raise InstagramError("Sessão expirada e sem senha salva. Reconecte a conta.")
        try:
            cl.login(account.username, pwd)
            media = _do()
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(_friendly(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        name = exc.__class__.__name__
        kind = "rate_limit" if name in ("PleaseWaitFewMinutes", "ClientThrottledError") else "error"
        raise InstagramError(_friendly(exc), kind=kind) from exc

    return {
        "media_pk": str(media.pk),
        "code": getattr(media, "code", ""),
        "settings": cl.get_settings(),
    }
