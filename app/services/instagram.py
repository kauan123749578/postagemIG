"""Camada de integração com o Instagram via instagrapi.

Substitui a antiga Graph API da Meta. Cada conta loga por usuário/senha
(ou sessionid do navegador), e a sessão é persistida em Account.session_json.
Os uploads usam o ARQUIVO LOCAL do vídeo/imagem (instagrapi não usa URL pública).
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import DATA_DIR, IMAGES_DIR, VIDEOS_DIR
from app.services.crypto import decrypt_secret

logger = logging.getLogger("instagram")

INSTAGRAM_CAPTION_MAX = 2200

TMP_DIR = DATA_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)


class InstagramAPIError(Exception):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


def _wrap(exc: Exception) -> "InstagramAPIError":
    return InstagramAPIError(_friendly(exc), {"ig_exc": exc.__class__.__name__})


def _friendly(exc: Exception) -> str:
    name = exc.__class__.__name__
    msg = str(exc) or name
    hints = {
        "BadPassword": "Usuário ou senha inválidos (ou IP bloqueado). Tente logar por sessionid.",
        "TwoFactorRequired": "Conta com 2FA. Informe o código de verificação (2FA).",
        "ChallengeRequired": "O Instagram pediu verificação extra. Faça login por sessionid do navegador.",
        "PleaseWaitFewMinutes": "Muitas tentativas. Aguarde alguns minutos antes de tentar de novo.",
        "LoginRequired": "Sessão expirada. Refaça o login da conta.",
        "ClientForbiddenError": "Ação bloqueada pelo Instagram. Aguarde e tente mais tarde.",
        "ClientThrottledError": "Limite do Instagram atingido. Aguarde antes de postar de novo.",
    }
    return f"{hints.get(name, msg)}"


def _raise_challenge_handler(username, choice):  # noqa: ANN001
    raise InstagramAPIError(
        "Verificação extra exigida pelo Instagram. Use login por sessionid do navegador."
    )


def _build_client(proxy_url: str | None = None):
    # Import tardio: instagrapi é pesado e só precisa em runtime.
    from instagrapi import Client

    cl = Client()
    cl.delay_range = [2, 5]
    cl.challenge_code_handler = _raise_challenge_handler
    if proxy_url and proxy_url.strip():
        try:
            cl.set_proxy(proxy_url.strip())
        except Exception as exc:  # noqa: BLE001
            raise InstagramAPIError(f"Proxy inválido: {exc}") from exc
    return cl


def _download_to_tmp(url: str) -> Path:
    ext = Path(urlparse(url).path).suffix or ".bin"
    dest = TMP_DIR / f"{uuid.uuid4().hex}{ext}"
    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
    except requests.RequestException as exc:
        raise InstagramAPIError(f"Não foi possível baixar o arquivo: {exc}") from exc
    return dest


def _resolve_local_path(url_or_path: str | None) -> Path | None:
    """Converte URL pública / caminho em um arquivo local existente."""
    if not url_or_path:
        return None
    value = str(url_or_path).strip()
    if not value:
        return None

    # Caminho local direto
    direct = Path(value)
    if direct.exists() and direct.is_file():
        return direct

    parsed = urlparse(value)
    path_part = parsed.path or value
    filename = Path(path_part).name

    # Mapeia /media/videos/<file> e /media/images/<file> para o volume local
    if "/media/videos/" in path_part or "/videos/" in path_part:
        candidate = VIDEOS_DIR / filename
        if candidate.exists():
            return candidate
    if "/media/images/" in path_part or "/images/" in path_part:
        candidate = IMAGES_DIR / filename
        if candidate.exists():
            return candidate

    # Procura o nome do arquivo nas duas pastas
    for folder in (VIDEOS_DIR, IMAGES_DIR):
        candidate = folder / filename
        if candidate.exists():
            return candidate

    # URL externa http(s): baixa para tmp
    if parsed.scheme in ("http", "https"):
        return _download_to_tmp(value)

    raise InstagramAPIError(f"Arquivo não encontrado para publicar: {filename}")


class InstagramClient:
    """Wrapper sobre instagrapi.Client com a mesma interface usada no painel."""

    def __init__(self, account):
        self.account = account
        self._cl = None

    # --- sessão ---
    def _load(self):
        if self._cl is not None:
            return self._cl
        cl = _build_client(self.account.proxy_url)
        if self.account.session_json:
            try:
                cl.set_settings(json.loads(self.account.session_json))
            except Exception:  # noqa: BLE001
                logger.warning("Sessão inválida da conta %s, será necessário novo login", self.account.id)
        self._cl = cl
        return cl

    def _sync_session(self) -> None:
        if self._cl is not None:
            try:
                self.account.session_json = json.dumps(self._cl.get_settings())
            except Exception:  # noqa: BLE001
                pass

    def _relogin(self) -> None:
        password = decrypt_secret(self.account.password_enc)
        if not (self.account.username and password):
            raise InstagramAPIError(
                "Sessão expirada e sem senha salva. Refaça o login da conta (sessionid ou senha)."
            )
        cl = self._cl or _build_client(self.account.proxy_url)
        try:
            cl.login(self.account.username, password)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc) from exc
        self._cl = cl
        self._sync_session()

    def _run(self, fn, *args, **kwargs):
        from instagrapi.exceptions import LoginRequired

        cl = self._load()
        try:
            result = fn(cl, *args, **kwargs)
        except LoginRequired:
            self._relogin()
            result = fn(self._cl, *args, **kwargs)
        except InstagramAPIError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc) from exc
        self._sync_session()
        return result

    # --- leitura ---
    def get_profile(self) -> dict[str, Any]:
        def _do(cl):
            info = cl.account_info()
            return {
                "username": info.username,
                "full_name": getattr(info, "full_name", ""),
                "follower_count": getattr(info, "follower_count", 0),
                "media_count": getattr(info, "media_count", 0),
            }

        return self._run(_do)

    def get_publishing_limit(self) -> dict[str, Any]:
        # instagrapi não tem limite de publicação da Meta.
        return {}

    def get_account_insights(self) -> dict[str, Any]:
        return {"data": []}

    def get_media_insights(self, media_id: str) -> dict[str, Any]:  # noqa: ARG002
        return {"data": []}

    # --- publicação ---
    def post_image(self, image_url: str, caption: str | None = None) -> str:
        path = _resolve_local_path(image_url)
        if not path:
            raise InstagramAPIError("Imagem não encontrada para publicar")

        def _do(cl):
            media = cl.photo_upload(path, caption or "")
            return str(media.pk)

        return self._run(_do)

    def post_reel(
        self,
        video_url: str,
        caption: str | None = None,
        *,
        cover_url: str | None = None,
        thumb_offset: int | None = None,  # noqa: ARG002 (compat)
        audio_name: str | None = None,  # noqa: ARG002 (compat)
    ) -> str:
        video_path = _resolve_local_path(video_url)
        if not video_path:
            raise InstagramAPIError("Vídeo não encontrado para publicar o Reel")
        thumb_path = _resolve_local_path(cover_url) if cover_url else None

        def _do(cl):
            kwargs = {}
            if thumb_path:
                kwargs["thumbnail"] = thumb_path
            media = cl.clip_upload(video_path, caption or "", **kwargs)
            return str(media.pk)

        return self._run(_do)

    def post_story(self, *, image_url: str | None = None, video_url: str | None = None) -> str:
        video_path = _resolve_local_path(video_url) if video_url else None
        image_path = _resolve_local_path(image_url) if image_url else None
        if not video_path and not image_path:
            raise InstagramAPIError("Envie uma imagem ou vídeo para o Story")

        def _do(cl):
            if video_path:
                media = cl.video_upload_to_story(video_path)
            else:
                media = cl.photo_upload_to_story(image_path)
            return str(media.pk)

        return self._run(_do)

    def post_carousel(self, media_urls: list[str], caption: str | None = None) -> str:
        paths = []
        for url in media_urls:
            path = _resolve_local_path(url)
            if not path:
                raise InstagramAPIError(f"Item do carrossel não encontrado: {url}")
            paths.append(path)

        def _do(cl):
            media = cl.album_upload(paths, caption or "")
            return str(media.pk)

        return self._run(_do)


def client_from_account(account) -> InstagramClient:
    return InstagramClient(account)


def login_account(
    account,
    *,
    password: str | None = None,
    sessionid: str | None = None,
    verification_code: str | None = None,
) -> dict[str, Any]:
    """Faz login (sessionid ou usuário/senha) e persiste a sessão na conta.

    Atualiza account.session_json e account.username. Não faz commit (o caller commita).
    Retorna o perfil básico da conta.
    """
    cl = _build_client(account.proxy_url)

    try:
        if sessionid and sessionid.strip():
            cl.login_by_sessionid(sessionid.strip())
        elif account.username and password:
            if verification_code and verification_code.strip():
                cl.login(account.username, password, verification_code=verification_code.strip())
            else:
                cl.login(account.username, password)
        else:
            raise InstagramAPIError(
                "Informe o sessionid OU usuário + senha para conectar a conta."
            )
    except InstagramAPIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _wrap(exc) from exc

    try:
        info = cl.account_info()
        account.username = info.username or account.username
    except Exception as exc:  # noqa: BLE001
        raise _wrap(exc) from exc

    account.session_json = json.dumps(cl.get_settings())
    return {
        "username": info.username,
        "full_name": getattr(info, "full_name", ""),
        "follower_count": getattr(info, "follower_count", 0),
        "media_count": getattr(info, "media_count", 0),
    }
