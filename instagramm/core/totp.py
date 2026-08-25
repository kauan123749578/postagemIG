"""TOTP (Google Authenticator) — gera código 2FA a partir do secret base32."""
from __future__ import annotations

import re
import time


def normalize_totp_secret(raw: str) -> str:
    """Limpa secret: remove espaços, hífens e prefixos otpauth://."""
    s = (raw or "").strip()
    if not s:
        return ""
    # otpauth://totp/...?secret=XXXX&...
    if s.lower().startswith("otpauth://"):
        m = re.search(r"[?&]secret=([A-Z2-7=]+)", s, re.I)
        if m:
            s = m.group(1)
    s = re.sub(r"[\s\-]+", "", s).upper()
    # só base32
    s = re.sub(r"[^A-Z2-7=]", "", s)
    return s


def totp_secret_valid(raw: str) -> bool:
    secret = normalize_totp_secret(raw)
    if len(secret) < 16:
        return False
    try:
        import pyotp

        pyotp.TOTP(secret).now()
        return True
    except Exception:  # noqa: BLE001
        return False


def generate_totp_code(raw: str, *, wait_if_expiring: bool = True) -> str:
    """Gera código de 6 dígitos. Se faltar <3s no ciclo, espera o próximo."""
    import pyotp

    secret = normalize_totp_secret(raw)
    if not secret:
        raise ValueError("Secret TOTP vazio")
    totp = pyotp.TOTP(secret)
    if wait_if_expiring:
        # ciclo de 30s — evita código que expira enquanto o request sobe
        remaining = 30 - (int(time.time()) % 30)
        if remaining <= 2:
            time.sleep(remaining + 0.15)
    code = totp.now()
    if not code or len(str(code)) < 6:
        raise ValueError("Falha ao gerar código TOTP")
    return str(code).zfill(6)
