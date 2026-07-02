"""Fluxo de verificação extra do Instagram (código por e-mail/SMS) durante o login."""
from __future__ import annotations

import threading
from typing import Callable

_lock = threading.Lock()
_waiting: dict[int, dict] = {}
_ui_hook: Callable[[int, str, str], None] | None = None


def set_ui_hook(fn: Callable[[int, str, str], None] | None) -> None:
    global _ui_hook
    _ui_hook = fn


def _choice_label(choice) -> str:
    from instagrapi.mixins.challenge import ChallengeChoice

    if choice == ChallengeChoice.EMAIL:
        return "e-mail"
    if choice == ChallengeChoice.SMS:
        return "SMS"
    return "verificação"


def wait_for_code(account_id: int, username: str, choice) -> str:
    """Bloqueia até o usuário digitar o código na UI (chamado pela instagrapi)."""
    label = _choice_label(choice)
    event = threading.Event()
    with _lock:
        _waiting[account_id] = {
            "event": event,
            "code": "",
            "choice": label,
            "username": username or "",
        }

    if _ui_hook:
        try:
            _ui_hook(account_id, username or "", label)
        except Exception:  # noqa: BLE001
            pass

    if not event.wait(timeout=300):
        with _lock:
            _waiting.pop(account_id, None)
        return ""

    with _lock:
        data = _waiting.pop(account_id, {})
    return (data.get("code") or "").strip()


def submit_code(account_id: int, code: str) -> bool:
    with _lock:
        data = _waiting.get(account_id)
        if not data:
            return False
        data["code"] = code.strip()
        data["event"].set()
    return True


def cancel_wait(account_id: int) -> None:
    with _lock:
        data = _waiting.pop(account_id, None)
    if data:
        data["event"].set()


def make_handler(account_id: int):
    def handler(username, choice):
        return wait_for_code(account_id, username, choice)

    return handler
