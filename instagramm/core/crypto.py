"""Cifragem das senhas das contas (Fernet com chave local persistente)."""
from cryptography.fernet import Fernet, InvalidToken

from core.config import KEY_PATH


def _load_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


_fernet = Fernet(_load_key())


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
