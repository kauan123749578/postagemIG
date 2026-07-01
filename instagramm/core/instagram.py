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


from core.proxy import normalize_proxy_url


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
        normalized = normalize_proxy_url(proxy_url)
        try:
            cl.set_proxy(normalized)
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


def load_session_file(path: str, proxy_url: str | None = None) -> dict[str, Any]:
    """Carrega um session.json da instagrapi, valida e devolve settings + perfil."""
    with open(path, "r", encoding="utf-8") as fh:
        settings = json.load(fh)
    cl = build_client(proxy_url, settings)
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


DEFAULT_COMMENTS = [
    "🔥", "👏", "incrível!", "top demais", "❤️", "muito bom!", "amei 😍",
    "perfeito 🔥", "que demais 👏", "sensacional!", "🙌", "show!", "👏👏👏",
]


def warm_session(
    account,
    *,
    likes: int = 3,
    stories: int = 3,
    follows: int = 0,
    saves: int = 0,
    comments: int = 0,
    story_likes: int = 0,
    unfollows: int = 0,
    scrolls: int = 1,
    hashtags: list[str] | None = None,
    comment_pool: list[str] | None = None,
) -> tuple[dict, dict]:
    """Simula atividade humana para 'aquecer' a conta.

    Ações (todas opcionais, randomizadas e com delays): rolar feed, curtir,
    salvar, comentar, ver stories, curtir stories, seguir e deixar de seguir.
    Cada ação é protegida — uma falha isolada não derruba o aquecimento.
    Retorna (resumo, settings).
    """
    import random
    import time

    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte antes de aquecer.")

    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)
    s = {
        "scrolls": 0, "liked": 0, "saved": 0, "commented": 0,
        "story_viewed": 0, "story_liked": 0, "followed": 0, "unfollowed": 0, "errors": 0,
    }
    pool = comment_pool or DEFAULT_COMMENTS

    def pause(a=2.0, b=6.0):
        time.sleep(random.uniform(a, b))

    # rolar o feed algumas vezes (simula scroll)
    for _ in range(max(1, scrolls)):
        try:
            cl.get_timeline_feed()
            s["scrolls"] += 1
            pause(2.0, 5.0)
        except Exception:  # noqa: BLE001
            s["errors"] += 1

    # coletar mídias de hashtags
    tags = list(hashtags or ["reels", "explore", "viral", "foryou"])
    random.shuffle(tags)
    medias = []
    for tag in tags[:2]:
        try:
            medias += cl.hashtag_medias_top(tag, amount=15)
            pause(1.5, 3.5)
        except Exception:  # noqa: BLE001
            s["errors"] += 1
    random.shuffle(medias)

    # autores únicos (para stories/follows)
    authors, seen = [], set()
    for m in medias:
        uid = getattr(getattr(m, "user", None), "pk", None)
        if uid and uid not in seen:
            seen.add(uid)
            authors.append(uid)

    # monta uma fila de ações e embaralha para parecer humano
    queue: list[tuple] = []
    for m in medias[: max(0, likes)]:
        queue.append(("like", m))
    for m in medias[: max(0, saves)]:
        queue.append(("save", m))
    for m in medias[: max(0, comments)]:
        queue.append(("comment", m))
    for uid in authors[: max(0, stories)]:
        queue.append(("story_view", uid))
    for uid in authors[: max(0, story_likes)]:
        queue.append(("story_like", uid))
    for uid in authors[: max(0, follows)]:
        queue.append(("follow", uid))
    random.shuffle(queue)

    for action, target in queue:
        try:
            if action == "like":
                cl.media_like(target.id); s["liked"] += 1
            elif action == "save":
                cl.media_save(target.id); s["saved"] += 1
            elif action == "comment":
                cl.media_comment(target.id, random.choice(pool)); s["commented"] += 1
            elif action == "story_view":
                st = cl.user_stories(target)
                if st:
                    cl.story_seen([x.pk for x in st]); s["story_viewed"] += 1
            elif action == "story_like":
                st = cl.user_stories(target)
                if st:
                    cl.story_like(st[0].id); s["story_liked"] += 1
            elif action == "follow":
                cl.user_follow(target); s["followed"] += 1
        except Exception:  # noqa: BLE001
            s["errors"] += 1
        pause()

    # deixar de seguir alguns (de quem a conta já segue)
    if unfollows > 0:
        try:
            uid = cl.user_id
            following = cl.user_following(uid, amount=max(30, unfollows * 6)) if uid else {}
            ids = list(following.keys())
            random.shuffle(ids)
            for fid in ids[: unfollows]:
                try:
                    cl.user_unfollow(fid); s["unfollowed"] += 1
                    pause(2.0, 6.0)
                except Exception:  # noqa: BLE001
                    s["errors"] += 1
        except Exception:  # noqa: BLE001
            s["errors"] += 1

    return s, cl.get_settings()


def post_reel(account, video_path: str, caption: str = "", cover_path: str | None = None) -> dict[str, Any]:
    """Publica um Reel usando a sessão salva da conta. Retorna {media_pk, code, settings}."""
    from instagrapi.exceptions import LoginRequired

    video = Path(video_path)
    if not video.exists():
        raise InstagramError(f"Vídeo não encontrado: {video_path}")
    thumb = Path(cover_path) if cover_path and Path(cover_path).exists() else None
    temp_thumb: Path | None = None
    if not thumb:
        from core.video_deps import make_video_thumbnail

        try:
            temp_thumb = make_video_thumbnail(video)
            thumb = temp_thumb
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(f"Falha ao gerar capa do vídeo: {exc}") from exc

    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte a conta antes de postar.")

    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)

    def _do():
        return cl.clip_upload(video, caption or "", thumbnail=thumb)

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
    finally:
        if temp_thumb and temp_thumb.is_file():
            try:
                temp_thumb.unlink()
            except OSError:
                pass

    return {
        "media_pk": str(media.pk),
        "code": getattr(media, "code", ""),
        "settings": cl.get_settings(),
    }
