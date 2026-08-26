"""Logger central de eventos: grava no banco e envia ao Telegram."""
from datetime import datetime, timezone

from core import telegram
from core.db import EventLog, SessionLocal

_ICONS = {"info": "ℹ️", "success": "✅", "error": "❌", "warm": "🔥", "warning": "⚠️"}


def log_event(message: str, level: str = "info", account: str = "") -> None:
    # grava no banco
    db = SessionLocal()
    try:
        db.add(EventLog(level=level, account=account or "", message=message))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()

    # envia ao telegram
    icon = _ICONS.get(level, "•")
    stamp = datetime.now(timezone.utc).astimezone().strftime("%d/%m %H:%M")
    head = f"{icon} <b>{account}</b>" if account else icon
    telegram.send(f"{head}\n{message}\n<i>{stamp}</i>")


def recent_events(limit: int = 100) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(EventLog).order_by(EventLog.created_at.desc()).limit(limit).all()
        return [{
            "level": r.level,
            "account": r.account,
            "message": r.message,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in rows]
    finally:
        db.close()


def clear_events() -> int:
    """Apaga todos os eventos do sistema. Retorna quantos foram removidos."""
    db = SessionLocal()
    try:
        n = db.query(EventLog).delete()
        db.commit()
        return int(n or 0)
    except Exception:  # noqa: BLE001
        db.rollback()
        raise
    finally:
        db.close()
