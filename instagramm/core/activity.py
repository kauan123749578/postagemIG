"""Status ao vivo de publicação — UI (Dashboard) escuta via subscribe."""
from __future__ import annotations

import threading
from typing import Any, Callable

_lock = threading.Lock()
_state: dict[str, Any] = {
    "active": False,
    "phase": "",
    "account": "",
    "message": "",
    "kind": "info",  # info | success | error
}
_listeners: list[Callable[[dict[str, Any]], None]] = []


def get() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def subscribe(callback: Callable[[dict[str, Any]], None]) -> None:
    with _lock:
        if callback not in _listeners:
            _listeners.append(callback)


def unsubscribe(callback: Callable[[dict[str, Any]], None]) -> None:
    with _lock:
        if callback in _listeners:
            _listeners.remove(callback)


def _emit() -> None:
    snapshot = get()
    for cb in list(_listeners):
        try:
            cb(snapshot)
        except Exception:  # noqa: BLE001
            pass


def set_posting(account: str, phase: str, message: str, *, kind: str = "info") -> None:
    """Atualiza o status da publicação em andamento."""
    with _lock:
        _state.update(
            {
                "active": True,
                "phase": phase or "",
                "account": (account or "").strip(),
                "message": message or "",
                "kind": kind or "info",
            }
        )
    _emit()


def clear(*, delay_message: str | None = None, kind: str = "info") -> None:
    """Encerra o status. Se delay_message for passado, emite um último frame e a UI some sozinha."""
    with _lock:
        if delay_message:
            phase = "done" if kind == "success" else ("error" if kind == "error" else "idle")
            _state.update(
                {
                    "active": False,
                    "phase": phase,
                    "message": delay_message,
                    "kind": kind,
                }
            )
        else:
            _state.update(
                {
                    "active": False,
                    "phase": "",
                    "account": "",
                    "message": "",
                    "kind": "info",
                }
            )
    _emit()
