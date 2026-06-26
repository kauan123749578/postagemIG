"""Envio de mensagens para o Telegram (logs do sistema)."""
import threading

import requests

from core import store

API = "https://api.telegram.org/bot{token}/sendMessage"


def is_enabled() -> bool:
    s = store.get_all_settings()
    return s.get("telegram_enabled") == "1" and bool(s.get("telegram_token")) and bool(s.get("telegram_chat_id"))


def _send_sync(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    try:
        resp = requests.post(
            API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            return False, data.get("description", "Erro desconhecido")
        return True, "ok"
    except requests.RequestException as exc:
        return False, str(exc)


def send(text: str) -> None:
    """Envia em background; ignora silenciosamente se não configurado."""
    s = store.get_all_settings()
    if s.get("telegram_enabled") != "1":
        return
    token, chat_id = s.get("telegram_token"), s.get("telegram_chat_id")
    if not token or not chat_id:
        return
    threading.Thread(target=_send_sync, args=(token, chat_id, text), daemon=True).start()


def test_connection(token: str, chat_id: str) -> tuple[bool, str]:
    return _send_sync(token, chat_id, "✅ <b>Postagem IG</b> conectado ao Telegram com sucesso!")
