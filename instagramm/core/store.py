"""Armazenamento simples de configurações em chave/valor."""
from core.db import Setting, SessionLocal

_DEFAULTS = {
    "telegram_token": "",
    "telegram_chat_id": "",
    "telegram_enabled": "0",
}


def get_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        if row is not None:
            return row.value
        return _DEFAULTS.get(key, default)
    finally:
        db.close()


def set_setting(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value or "")
            db.add(row)
        else:
            row.value = value or ""
        db.commit()
    finally:
        db.close()


def get_all_settings() -> dict:
    db = SessionLocal()
    try:
        data = dict(_DEFAULTS)
        for row in db.query(Setting).all():
            data[row.key] = row.value
        return data
    finally:
        db.close()
