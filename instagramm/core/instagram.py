"""Wrapper da instagrapi: login (usuário/senha + 2FA, ou sessionid), sessão e upload local."""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("instagram")


class InstagramError(Exception):
    def __init__(
        self,
        message: str,
        kind: str = "error",
        settings: dict | None = None,
        pending_2fa: dict | None = None,
    ):
        super().__init__(message)
        self.kind = kind  # error / two_factor / challenge / rate_limit
        self.settings = settings  # device/uuids para reaproveitar no envio do 2FA
        self.pending_2fa = pending_2fa  # estado completo p/ 2FA rápido (context + last_json)


def _friendly(exc: Exception) -> str:
    name = exc.__class__.__name__
    raw = str(exc) or name
    low = raw.lower()
    if "email or confirmed phone" in low or "email" in low and "confirmed phone" in low:
        return "Conta sem e-mail ou telefone confirmado no Instagram. Confirme no app oficial antes de editar."
    if "chat not found" in low:
        pass
    if "exceeded" in low and "redirect" in low:
        return (
            "Sessão ou proxy inválido (muitos redirecionamentos). "
            "Reconecte em Contas com sessionid novo ou revise o proxy (tente socks5://)."
        )
    if "login_required" in low:
        return "Sessão expirada. Reconecte em Contas (cole um sessionid novo do navegador)."
    if low in ("challenge", "challenge_required") or "challenge_required" in low:
        return (
            "O Instagram pediu verificação extra (código por e-mail ou SMS). "
            "Aguarde o popup e digite o código."
        )
    hints = {
        "BadPassword": "Usuário ou senha inválidos.",
        "TwoFactorRequired": "Conta com verificação em duas etapas (2FA).",
        "ChallengeRequired": (
            "O Instagram pediu verificação extra (código por e-mail ou SMS). "
            "Aguarde o popup e digite o código."
        ),
        "PleaseWaitFewMinutes": "Muitas tentativas. Aguarde alguns minutos.",
        "LoginRequired": "Sessão expirada. Refaça o login em Contas.",
        "ClientThrottledError": "Limite do Instagram atingido. Aguarde antes de postar.",
        "ProxyAddressIsBlocked": "Proxy bloqueado pelo Instagram.",
    }
    if "verification" in low and ("invalid" in low or "incorrect" in low or "wrong" in low):
        return "Código 2FA inválido ou expirado. Gere um código novo no app e tente de novo."
    if "two_factor" in low and ("invalid" in low or "incorrect" in low):
        return "Código 2FA inválido ou expirado. Gere um código novo no app e tente de novo."
    if name in hints:
        return hints[name]
    # erros JSON/dict da API
    if raw.startswith("{") and "errors" in raw:
        try:
            import ast
            data = ast.literal_eval(raw)
            errs = data.get("errors") if isinstance(data, dict) else None
            if isinstance(errs, list) and errs:
                return str(errs[0])
        except Exception:  # noqa: BLE001
            pass
    return raw


from core.proxy import normalize_proxy_url


def _ensure_phantom_path() -> None:
    """Garante que a pasta phantom/ (irmã de instagramm/) está no sys.path."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]  # postagemIG/
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def _new_client():
    """EnhancedClient (Phantom) com fallback para Client stock."""
    from instagrapi import Client

    _ensure_phantom_path()
    try:
        from phantom import EnhancedClient

        cl = EnhancedClient(debug=False, auto_track_nav=True)
        logger.info("Cliente = Phantom EnhancedClient (TLS + headers + CAA)")
        return cl
    except Exception as exc:  # noqa: BLE001
        logger.warning("Phantom indisponível (%s) — usando Client stock", exc)
        return Client()


def build_client(
    proxy_url: str | None = None,
    settings: dict | None = None,
    account_id: int | None = None,
    device_key: str | None = None,
    *,
    fast: bool = False,
):
    from core.device import apply_device, pick_device_key_for_new_account, used_device_keys_from_accounts

    cl = _new_client()
    # Login/2FA: delays baixos — TOTP expira em ~30s; [2,5]s por request estourava o código
    cl.delay_range = [0, 0.4] if fast else [1, 2]
    if settings:
        # Fluxo 2FA / sessão salva: NÃO troca o device
        try:
            cl.set_settings(settings)
        except Exception:  # noqa: BLE001
            logger.warning("Não foi possível carregar settings de sessão")
        if hasattr(cl, "_header_builder"):
            cl._header_builder = None
        try:
            from core.device import device_key_from_settings

            cl._assigned_device_key = device_key_from_settings(settings)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    else:
        # Login novo: escolhe modelo do pool (Samsung incluso; conta nova ≠ troca em conta velha)
        key = (device_key or "").strip()
        if not key:
            used: list[str] = []
            try:
                from core.db import Account, SessionLocal

                db = SessionLocal()
                try:
                    rows = db.query(Account).all()
                    used = used_device_keys_from_accounts(rows)
                finally:
                    db.close()
            except Exception:  # noqa: BLE001
                used = []
            key = pick_device_key_for_new_account(used)
        apply_device(cl, key)
        try:
            cl.set_locale("pt_BR")
            cl.set_country("BR")
            cl.set_country_code(55)
            cl.set_timezone_offset(-3 * 60 * 60)
        except Exception:  # noqa: BLE001
            pass
        if hasattr(cl, "_header_builder"):
            cl._header_builder = None
        # expõe a key escolhida para o caller gravar na conta
        try:
            cl._assigned_device_key = key  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    if proxy_url and proxy_url.strip():
        normalized = normalize_proxy_url(proxy_url)
        try:
            cl.set_proxy(normalized)
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(f"Proxy inválido: {exc}") from exc
    if account_id is not None:
        from core.challenge_flow import make_handler

        cl.challenge_code_handler = make_handler(account_id)
    return cl


def _capture_2fa_state(cl) -> dict:
    """Guarda device + last_json + context Bloks para enviar o código sem refazer login."""
    from copy import deepcopy

    last_json = deepcopy(getattr(cl, "last_json", None) or {})
    if not isinstance(last_json, dict):
        last_json = {}
    context = ""
    if hasattr(cl, "bloks_extract_two_step_verification_context"):
        try:
            context = cl.bloks_extract_two_step_verification_context(last_json) or ""
        except Exception:  # noqa: BLE001
            context = ""
    if not context and hasattr(cl, "_extract_two_step_verification_context"):
        try:
            context = cl._extract_two_step_verification_context(last_json) or ""
        except Exception:  # noqa: BLE001
            context = ""
    return {
        "settings": cl.get_settings(),
        "last_json": last_json,
        "two_step_context": context,
    }


def _login_result_payload(cl, device_key: str | None = None) -> dict[str, Any]:
    assigned = getattr(cl, "_assigned_device_key", None) or device_key or ""
    info = None
    try:
        info = cl.account_info()
    except Exception:  # noqa: BLE001
        info = None
    username = (getattr(info, "username", None) or getattr(cl, "username", None) or "")
    return {
        "settings": cl.get_settings(),
        "username": username,
        "full_name": getattr(info, "full_name", "") if info else "",
        "follower_count": getattr(info, "follower_count", 0) if info else 0,
        "media_count": getattr(info, "media_count", 0) if info else 0,
        "device_key": assigned,
    }


def complete_two_factor(
    *,
    username: str,
    password: str,
    verification_code: str,
    pending: dict,
    proxy_url: str | None = None,
    account_id: int | None = None,
    device_key: str | None = None,
) -> dict[str, Any]:
    """Envia código 2FA sem refazer login Bloks inteiro (evita expirar o TOTP)."""
    from copy import deepcopy
    from uuid import uuid4

    from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired

    code = (verification_code or "").strip()
    if not code:
        raise InstagramError("Informe o código 2FA.")

    settings = pending.get("settings") if isinstance(pending.get("settings"), dict) else pending
    last_json = pending.get("last_json") or {}
    context = (pending.get("two_step_context") or "").strip()

    cl = build_client(proxy_url, settings, account_id=account_id, device_key=device_key, fast=True)
    cl.username = username
    cl.password = password
    if last_json:
        cl.last_json = deepcopy(last_json)

    try:
        logged = False

        # Caminho rápido Bloks (Phantom): só valida o código, não repete senha + pre-login
        if context and hasattr(cl, "bloks_two_step_verification_verify_code"):
            _ensure_phantom_path()
            from phantom.login import LoginFlow

            flow = LoginFlow(cl)
            flow.waterfall_id = pending.get("waterfall_id") or str(uuid4())
            result = flow._handle_two_factor(context, code)
            logged = flow._apply_login(result)
            if logged:
                cl.last_login = __import__("time").time()

        # Legacy: two_factor_login direto com identifier salvo
        elif isinstance(last_json, dict) and last_json.get("two_factor_info", {}).get("two_factor_identifier"):
            tfi = last_json["two_factor_info"]["two_factor_identifier"]
            data = {
                "verification_code": code,
                "phone_id": cl.phone_id,
                "_csrftoken": cl.token,
                "two_factor_identifier": tfi,
                "username": username,
                "trust_this_device": "0",
                "guid": cl.uuid,
                "device_id": cl.android_device_id,
                "waterfall_id": str(uuid4()),
                "verification_method": "3",
            }
            cl.private_request("accounts/two_factor_login/", data, login=True)
            if hasattr(cl, "last_response") and cl.last_response is not None:
                hdr = cl.last_response.headers.get("ig-set-authorization")
                if hdr and hasattr(cl, "parse_authorization"):
                    cl.authorization_data = cl.parse_authorization(hdr)
            logged = True
            cl.last_login = __import__("time").time()

        else:
            # Fallback: login completo, mas sem post-login pesado
            noop = lambda: True  # noqa: E731
            if hasattr(cl, "login_flow"):
                cl.login_flow = noop
            logged = bool(cl.login(username, password, verification_code=code))

        if not logged:
            raise InstagramError(
                "Código 2FA inválido ou expirado. Gere um código novo no app.",
                kind="two_factor",
                pending_2fa=_capture_2fa_state(cl),
            )
        return _login_result_payload(cl, device_key)

    except TwoFactorRequired as exc:
        pending_new = _capture_2fa_state(cl)
        raise InstagramError(
            _friendly(exc),
            kind="two_factor",
            settings=pending_new.get("settings"),
            pending_2fa=pending_new,
        ) from exc
    except ChallengeRequired as exc:
        raise InstagramError(_friendly(exc), kind="challenge", settings=cl.get_settings()) from exc
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InstagramError(_friendly(exc)) from exc


def login(
    *,
    username: str | None = None,
    password: str | None = None,
    sessionid: str | None = None,
    verification_code: str | None = None,
    proxy_url: str | None = None,
    settings: dict | None = None,
    account_id: int | None = None,
    device_key: str | None = None,
) -> dict[str, Any]:
    """Loga e retorna {settings, username, full_name, ...}. Levanta InstagramError."""
    from instagrapi.exceptions import (
        ChallengeRequired,
        TwoFactorRequired,
    )

    cl = build_client(
        proxy_url, settings, account_id=account_id, device_key=device_key,
        fast=bool((verification_code or "").strip()),
    )

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
        pending = _capture_2fa_state(cl)
        raise InstagramError(
            _friendly(exc),
            kind="two_factor",
            settings=pending.get("settings"),
            pending_2fa=pending,
        ) from exc
    except ChallengeRequired as exc:
        msg = _friendly(exc)
        if not msg or msg.lower() in ("challenge", "challenge_required"):
            msg = (
                "O Instagram pediu verificação extra (código por e-mail ou SMS). "
                "Aguarde o popup e digite o código."
            )
        raise InstagramError(msg, kind="challenge", settings=cl.get_settings()) from exc
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InstagramError(_friendly(exc)) from exc

    return _login_result_payload(cl, device_key)


def _client_from_account(account, settings: dict, *, use_proxy: bool = True):
    proxy = account.proxy_url if use_proxy else None
    cl = build_client(proxy, settings)
    if not cl.user_id:
        sid = _extract_sessionid(settings) or _saved_sessionid(account)
        if sid:
            try:
                cl.login_by_sessionid(sid)
            except Exception:  # noqa: BLE001
                pass
    if hasattr(cl, "inject_sessionid_to_public"):
        try:
            cl.inject_sessionid_to_public()
        except Exception:  # noqa: BLE001
            pass
    return cl


def _extract_sessionid(settings: dict | None) -> str | None:
    """Tenta obter sessionid dos settings da instagrapi."""
    if not settings:
        return None
    auth = settings.get("authorization_data") or {}
    sid = auth.get("sessionid")
    if sid:
        return str(sid).strip()
    cookies = settings.get("cookies") or {}
    if isinstance(cookies, dict):
        for key, val in cookies.items():
            if key == "sessionid" and val:
                return str(val).strip()
            if isinstance(val, dict) and val.get("name") == "sessionid":
                v = val.get("value")
                if v:
                    return str(v).strip()
    return None


def _saved_sessionid(account) -> str | None:
    from core.crypto import decrypt_secret

    sid = decrypt_secret(getattr(account, "sessionid_enc", "") or "") or None
    if sid:
        return sid.strip()
    if account.session_json:
        try:
            return _extract_sessionid(json.loads(account.session_json))
        except Exception:  # noqa: BLE001
            pass
    return None


def _needs_relogin(exc: Exception) -> bool:
    """Detecta erro real de sessão (não confundir com proxy/redirect)."""
    from instagrapi.exceptions import ClientLoginRequired, LoginRequired

    if isinstance(exc, (LoginRequired, ClientLoginRequired)):
        return True
    low = str(exc).lower()
    if "login_required" in low or "logged out" in low:
        return True
    err = getattr(exc, "error_response", None)
    if isinstance(err, dict) and str(err.get("message", "")).lower() == "login_required":
        return True
    return False


def _raise_api_error(exc: Exception) -> None:
    """Converte exceção da API em InstagramError com mensagem útil."""
    from requests.exceptions import TooManyRedirects

    if isinstance(exc, TooManyRedirects):
        raise InstagramError(_friendly(exc), kind="error") from exc
    detail = _friendly(exc)
    if _needs_relogin(exc):
        raise InstagramError(
            f"Não foi possível editar o perfil: {detail}. "
            "Tente reconectar em Contas (senha costuma funcionar melhor que sessionid para editar bio).",
            kind="login_required",
        ) from exc
    raise InstagramError(detail, kind="error") from exc


def _relogin_fresh(account) -> dict:
    """Faz login do zero e devolve settings atualizados."""
    from core.crypto import decrypt_secret

    pwd = decrypt_secret(account.password_enc) or None
    sid = _saved_sessionid(account)
    cl = build_client(account.proxy_url, None)
    try:
        if account.username and pwd:
            cl.login(account.username, pwd)
        elif sid:
            cl.login_by_sessionid(sid)
        else:
            raise InstagramError(
                "Sessão expirada. Reconecte em Contas (senha ou sessionid).",
                kind="login_required",
            )
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        kind = "login_required" if _needs_relogin(exc) else "error"
        raise InstagramError(_friendly(exc), kind=kind) from exc
    return cl.get_settings()


def _relogin(account, cl) -> None:
    """Compat: atualiza o client existente após relogar."""
    settings = _relogin_fresh(account)
    try:
        cl.set_settings(settings)
    except Exception:  # noqa: BLE001
        pass


def _run_authed(account, callback, *, preserve_session: bool = False, use_proxy: bool = True):
    """Executa ação com a sessão salva — sem relogin automático."""
    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte a conta.")
    original_settings = json.loads(account.session_json)
    cl = _client_from_account(account, original_settings, use_proxy=use_proxy)
    try:
        result = callback(cl)
        settings = original_settings if preserve_session else cl.get_settings()
        return result, settings
    except InstagramError:
        raise
    except Exception as exc:
        _raise_api_error(exc)


def _classify_health_error(exc: Exception) -> tuple[str, str]:
    """Classifica falha de verificação: banned | expired | challenge | error."""
    from instagrapi.exceptions import (
        ChallengeRequired,
        ClientLoginRequired,
        FeedbackRequired,
        LoginRequired,
        SentryBlock,
        UserNotFound,
    )

    name = exc.__class__.__name__
    raw = str(exc) or name
    low = raw.lower()
    err = getattr(exc, "error_response", None)
    if isinstance(err, dict):
        low = f"{low} {json.dumps(err).lower()}"

    ban_hints = (
        "has been disabled",
        "account has been disabled",
        "user is inactive",
        "inactive user",
        "suspended",
        "we disabled your account",
        "your account was disabled",
        "violat",
        "account is disabled",
        "user not found",
        "usuario desativado",
        "conta desativada",
        "foi desativada",
        "foi desabilitada",
    )
    challenge_hints = (
        "challenge_required",
        "checkpoint_required",
        "checkpoint",
        "challenge",
        "bloks",
    )

    if isinstance(exc, (FeedbackRequired, SentryBlock)) or any(h in low for h in ban_hints):
        # FeedbackRequired / SentryBlock muitas vezes = restrição/ban
        if "feedback_required" in low or "sentry" in low or any(h in low for h in ban_hints):
            if any(h in low for h in ban_hints) or "disabled" in low or "suspended" in low:
                return (
                    "banned",
                    "Conta com ban/desativada no Instagram (ou removida). Confira no app oficial.",
                )
            # feedback genérico — tratar como ban/restrição forte
            if isinstance(exc, (FeedbackRequired, SentryBlock)):
                return (
                    "banned",
                    "Instagram bloqueou a conta (feedback/restrição). Pode ser ban temporário ou permanente.",
                )

    if isinstance(exc, UserNotFound) or name == "UserNotFound":
        return (
            "banned",
            "Usuário não encontrado — conta pode ter sido banida ou o @ mudou.",
        )

    if isinstance(exc, ChallengeRequired) or any(h in low for h in challenge_hints):
        if "login_required" not in low:
            return (
                "challenge",
                "Checkpoint/challenge do Instagram — abra o app oficial e complete a verificação.",
            )

    if isinstance(exc, (LoginRequired, ClientLoginRequired)) or _needs_relogin(exc):
        return (
            "expired",
            "Sessão caiu (login_required). Conta ainda pode existir — reconecte em Contas.",
        )

    return ("error", _friendly(exc))


def verify_session(account) -> dict[str, Any]:
    """Confere se a sessão salva ainda é válida."""
    if not account.session_json:
        raise InstagramError("Conta sem sessão. Conecte novamente.", kind="expired")
    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)
    try:
        info = cl.account_info()
    except Exception as exc:  # noqa: BLE001
        kind, msg = _classify_health_error(exc)
        raise InstagramError(msg, kind=kind) from exc
    return {
        "settings": cl.get_settings(),
        "username": info.username,
        "follower_count": getattr(info, "follower_count", 0),
        "media_count": getattr(info, "media_count", 0),
    }


def probe_account_health(account) -> dict[str, Any]:
    """Verifica saúde da conta: healthy / expired / banned / challenge / error.

    1) Testa sessão (account_info).
    2) Se sessão caiu, tenta ver se o @ ainda existe (user_id_from_username)
       para distinguir ban vs só sessão expirada.
    """
    username = (getattr(account, "username", "") or "").strip().lstrip("@")
    if not account.session_json:
        return {
            "status": "error",
            "kind": "error",
            "message": "Conta sem sessão salva. Conecte em Contas.",
            "username": username,
        }

    settings = json.loads(account.session_json)
    cl = _client_from_account(account, settings)

    try:
        info = cl.account_info()
        # confirma o próprio perfil
        try:
            if cl.user_id:
                cl.user_info(cl.user_id)
        except Exception:  # noqa: BLE001
            pass
        return {
            "status": "healthy",
            "kind": "healthy",
            "message": "Conta OK — sessão válida",
            "username": info.username or username,
            "follower_count": getattr(info, "follower_count", 0),
            "media_count": getattr(info, "media_count", 0),
            "settings": cl.get_settings(),
        }
    except Exception as exc:  # noqa: BLE001
        kind, msg = _classify_health_error(exc)

        # Sessão caiu: checa se o @ ainda existe (ban vs só logout)
        if kind == "expired" and username:
            try:
                from core.device import apply_device

                probe = _new_client()
                apply_device(probe, "samsung_m04")
                if account.proxy_url and str(account.proxy_url).strip():
                    try:
                        probe.set_proxy(normalize_proxy_url(account.proxy_url))
                    except Exception:  # noqa: BLE001
                        pass
                uid = probe.user_id_from_username(username)
                if not uid:
                    kind = "banned"
                    msg = (
                        f"@{username} não encontrado — provável ban/desativação. "
                        "Confira no Instagram oficial."
                    )
                else:
                    msg = (
                        f"Sessão caiu, mas @{username} ainda existe. "
                        "Reconecte em Contas (não parece ban)."
                    )
            except Exception as probe_exc:  # noqa: BLE001
                pkind, pmsg = _classify_health_error(probe_exc)
                if pkind == "banned":
                    kind = "banned"
                    msg = pmsg
                # se o probe falhar por rate limit / rede, mantém "expired"

        return {
            "status": kind if kind in ("banned", "expired", "challenge", "error") else "error",
            "kind": kind,
            "message": msg,
            "username": username,
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
    from core import activity

    video = Path(video_path)
    if not video.exists():
        raise InstagramError(f"Vídeo não encontrado: {video_path}")

    label = getattr(account, "username", None) or getattr(account, "name", None) or ""
    if getattr(account, "username", None):
        label = f"@{account.username}"

    cleaned: Path | None = None
    try:
        from core.video_deps import strip_video_metadata

        activity.set_posting(label, "clean", "Limpando metadados do vídeo…")
        cleaned = strip_video_metadata(video)
        upload_video = cleaned
        logger.info("Reel sem metadados: %s → %s", video.name, cleaned.name)
        activity.set_posting(label, "clean_done", "Metadados limpos — preparando envio…")
    except Exception as exc:  # noqa: BLE001
        # se ffmpeg falhar, publica o original (melhor do que bloquear o post)
        logger.warning("Não limpou metadados (%s) — usando vídeo original", exc)
        upload_video = video
        activity.set_posting(
            label, "clean_skip", "Não limpou metadados — enviando original…", kind="info"
        )

    thumb = Path(cover_path) if cover_path and Path(cover_path).exists() else None
    temp_thumb: Path | None = None
    if not thumb:
        from core.video_deps import make_video_thumbnail

        try:
            activity.set_posting(label, "thumb", "Gerando capa do vídeo…")
            temp_thumb = make_video_thumbnail(upload_video)
            thumb = temp_thumb
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(f"Falha ao gerar capa do vídeo: {exc}") from exc

    try:
        activity.set_posting(label, "upload", "Enviando Reel ao Instagram…")

        def work(cl):
            return cl.clip_upload(upload_video, caption or "", thumbnail=thumb)

        media, settings = _run_authed(account, work)
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        name = exc.__class__.__name__
        kind = "rate_limit" if name in ("PleaseWaitFewMinutes", "ClientThrottledError") else "error"
        if _needs_relogin(exc):
            kind = "login_required"
        raise InstagramError(_friendly(exc), kind=kind) from exc
    finally:
        for p in (temp_thumb, cleaned):
            if p and p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    return {
        "media_pk": str(media.pk),
        "code": getattr(media, "code", ""),
        "settings": settings,
    }


_STORY_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
_STORY_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _story_media_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _STORY_VIDEO_EXT:
        return "video"
    if ext in _STORY_PHOTO_EXT:
        return "photo"
    raise InstagramError(f"Formato não suportado para Story: {ext or '(sem extensão)'}")


def _normalize_link(link: str) -> str:
    """Garante que o link tenha esquema http/https."""
    link = (link or "").strip()
    if not link:
        return ""
    if not link.lower().startswith(("http://", "https://")):
        link = "https://" + link
    return link


def post_story(
    account,
    media_path: str,
    caption: str = "",
    link: str | dict | None = None,
) -> dict[str, Any]:
    """Publica foto ou vídeo como Story, com link opcional e sticker queimado."""
    media = Path(media_path)
    if not media.exists():
        raise InstagramError(f"Mídia não encontrada: {media_path}")
    kind = _story_media_kind(media)

    link_info: dict | None = None
    if isinstance(link, dict):
        link_info = link
    elif link:
        link_info = {"url": _normalize_link(str(link)), "x": 0.5, "y": 0.8}

    story_links = []
    upload_path = media
    stamped_temp: Path | None = None
    thumb_override: Path | None = None

    if link_info and link_info.get("url"):
        from instagrapi.types import StoryLink

        from core import story_sticker as ss

        url = _normalize_link(str(link_info["url"]))
        lx = float(link_info.get("x", 0.5))
        ly = float(link_info.get("y", 0.8))
        lw = float(link_info.get("width", link_info.get("link_w", 0.6)))
        lh = float(link_info.get("height", link_info.get("link_h", ss.STICKER_NORM_H)))

        try:
            stamped, geom = ss.prepare_story_image(
                media,
                {
                    "url": url,
                    "text": str(link_info.get("text") or ""),
                    "x": lx,
                    "y": ly,
                },
            )
            stamped_temp = stamped
            if geom:
                lw = geom["width"]
                lh = geom["height"]
            if kind == "photo":
                upload_path = stamped
            else:
                thumb_override = stamped
            story_links = [
                StoryLink(webUri=url, x=lx, y=ly, width=lw, height=lh, rotation=0.0)
            ]
        except Exception as exc:  # noqa: BLE001
            raise InstagramError(f"Erro ao preparar sticker de link: {exc}") from exc

    temp_thumb: Path | None = None
    try:

        def work(cl):
            nonlocal temp_thumb
            if kind == "photo":
                return cl.photo_upload_to_story(upload_path, caption or "", links=story_links)
            thumb = thumb_override
            if thumb is None:
                from core.video_deps import make_video_thumbnail

                try:
                    temp_thumb = make_video_thumbnail(media)
                    thumb = temp_thumb
                except Exception:  # noqa: BLE001
                    thumb = None
            return cl.video_upload_to_story(media, caption or "", thumbnail=thumb, links=story_links)

        story, settings = _run_authed(account, work)
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        name = exc.__class__.__name__
        exc_kind = "rate_limit" if name in ("PleaseWaitFewMinutes", "ClientThrottledError") else "error"
        if _needs_relogin(exc):
            exc_kind = "login_required"
        raise InstagramError(_friendly(exc), kind=exc_kind) from exc
    finally:
        for p in (temp_thumb, stamped_temp):
            if p and p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    return {
        "media_pk": str(story.pk),
        "code": getattr(story, "code", ""),
        "settings": settings,
        "kind": kind,
    }

BIO_MAX_LEN = 150


def update_profile(
    account,
    *,
    biography: str | None = None,
    picture_path: str | None = None,
) -> dict[str, Any]:
    """Atualiza bio e/ou foto de perfil via instagrapi."""
    bio = None if biography is None else str(biography).strip()
    pic = Path(picture_path) if picture_path else None

    if bio is None and not pic:
        raise InstagramError("Informe a bio e/ou a foto de perfil.")
    if bio is not None and len(bio) > BIO_MAX_LEN:
        raise InstagramError(f"Bio com no máximo {BIO_MAX_LEN} caracteres (agora: {len(bio)}).")
    if pic is not None:
        if not pic.exists():
            raise InstagramError(f"Foto não encontrada: {picture_path}")
        if pic.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise InstagramError("Use jpg, png ou webp para a foto de perfil.")

    changed: list[str] = []

    def work(cl):
        out: dict[str, Any] = {}
        if bio is not None:
            ok = cl.account_set_biography(bio)
            if not ok:
                cl.account_edit(biography=bio)
            out["biography"] = bio
            changed.append("bio")
        if pic is not None:
            user = cl.account_change_picture(pic)
            out["picture_ok"] = True
            out["username"] = getattr(user, "username", "") or ""
            changed.append("foto")
        return out

    try:
        result, settings = _run_authed(account, work)
    except InstagramError:
        raise
    except Exception as exc:  # noqa: BLE001
        kind = "login_required" if _needs_relogin(exc) else "error"
        raise InstagramError(_friendly(exc), kind=kind) from exc

    return {
        **result,
        "changed": changed,
        "settings": settings,
    }
