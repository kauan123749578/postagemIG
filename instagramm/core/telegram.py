"""Envio de mensagens para o Telegram (logs do sistema)."""
import threading

import requests

from core import store

API = "https://api.telegram.org/bot{token}/sendMessage"
ME_API = "https://api.telegram.org/bot{token}/getMe"


def is_enabled() -> bool:
    s = store.get_all_settings()
    return s.get("telegram_enabled") == "1" and bool(s.get("telegram_token")) and bool(s.get("telegram_chat_id"))


def _friendly(desc: str) -> str:
    d = (desc or "").lower()
    if "chat not found" in d:
        return ("Chat não encontrado. Checklist: 1) adicione o bot ao grupo/canal; "
                "2) num grupo, mande qualquer mensagem ou /start com o bot lá dentro; "
                "3) confira o Chat ID (grupo/supergrupo começa com -100). "
                "Em canais, deixe o bot como administrador.")
    if "bot was blocked" in d or "blocked" in d:
        return "O bot foi bloqueado. Desbloqueie o bot e envie /start para ele."
    if "unauthorized" in d:
        return "Token inválido. Confira o token gerado pelo @BotFather."
    if "not enough rights" in d or "administrator" in d:
        return "O bot precisa ser administrador do canal/grupo para enviar mensagens."
    return desc or "Erro desconhecido"


def _send_sync(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    try:
        resp = requests.post(
            API.format(token=token.strip()),
            json={"chat_id": chat_id.strip(), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            return False, _friendly(data.get("description", ""))
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


def _get_me(token: str) -> tuple[bool, str]:
    """Valida o token e devolve o @username do bot."""
    try:
        resp = requests.get(ME_API.format(token=token.strip()), timeout=15)
        data = resp.json()
        if not data.get("ok"):
            return False, _friendly(data.get("description", ""))
        return True, data["result"].get("username", "?")
    except requests.RequestException as exc:
        return False, str(exc)


def test_connection(token: str, chat_id: str) -> tuple[bool, str]:
    token, chat_id = token.strip(), chat_id.strip()
    # 1) confirma o token e descobre qual bot é
    ok, username = _get_me(token)
    if not ok:
        return False, f"Token inválido: {username}"

    # 2) tenta enviar a mensagem de teste
    sent, msg = _send_sync(token, chat_id, f"✅ <b>Postagem IG</b> conectado! (bot @{username})")
    if sent:
        return True, f"Mensagem enviada pelo bot @{username}"

    # 3) erro de acesso ao chat → diz exatamente qual bot precisa estar no grupo
    if "não encontrado" in msg.lower() or "chat not found" in msg.lower():
        return False, (
            f"O bot @{username} não está nesse chat. Adicione exatamente @{username} ao grupo "
            f"(não outro bot) e confirme que o Chat ID {chat_id} é desse grupo."
        )
    return False, msg
