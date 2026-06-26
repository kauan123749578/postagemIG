import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_SECRET = os.getenv("SECRET_KEY", "") or os.getenv("ADMIN_PASSWORD", "") or "postagem-ig-default-key"


def _fernet() -> Fernet:
    digest = hashlib.sha256(_SECRET.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
