"""Normaliza formatos comuns de proxy para URL que requests/instagrapi entendem."""
import re
from urllib.parse import quote, urlparse


def normalize_proxy_url(raw: str) -> str:
    """Aceita vários formatos e devolve uma URL de proxy válida.

    Formatos suportados:
      - ip:porta:usuario:senha   (comum em proxies residenciais)
      - usuario:senha@ip:porta
      - http://usuario:senha@ip:porta
      - socks5://usuario:senha@ip:porta
      - ip:porta  (sem autenticação)
    """
    s = (raw or "").strip()
    if not s:
        return ""

    # já tem esquema (http, https, socks5)
    if re.match(r"^(https?|socks5h?|socks4)://", s, re.I):
        return s

    # usuario:senha@host:porta (sem esquema)
    if "@" in s:
        return f"http://{s}"

    parts = s.split(":")
    # ip:porta:usuario:senha  (formato mais comum de fornecedores)
    if len(parts) >= 4 and parts[1].isdigit():
        host, port, user = parts[0], parts[1], parts[2]
        passwd = ":".join(parts[3:])  # senha pode conter ':'
        user_q = quote(user, safe="")
        pass_q = quote(passwd, safe="")
        return f"http://{user_q}:{pass_q}@{host}:{port}"

    # ip:porta (sem autenticação)
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"

    return f"http://{s}"


def proxy_label(url: str) -> str:
    """Texto curto para exibir na UI (esconde a senha)."""
    if not url:
        return ""
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = p.hostname or "?"
        port = f":{p.port}" if p.port else ""
        user = p.username or ""
        if user:
            return f"{user}@{host}{port}"
        return f"{host}{port}"
    except Exception:  # noqa: BLE001
        return "proxy configurado"
