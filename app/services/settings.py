from sqlalchemy.orm import Session

from app.models import Account, AppSetting

DEFAULTS = {
    "max_accounts": "50",
    "default_max_posts_per_day": "100",
    "default_max_posts_per_hour": "25",
    "default_loop_batch_size": "4",
    "default_loop_interval_seconds": "60",
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row:
        return row.value
    return DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def get_all_settings(db: Session) -> dict[str, str]:
    result = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        result[row.key] = row.value
    return result


def can_add_account(db: Session) -> tuple[bool, str]:
    max_accounts = int(get_setting(db, "max_accounts") or "50")
    current = db.query(Account).count()
    if current >= max_accounts:
        return False, f"Limite de contas atingido ({current}/{max_accounts})"
    return True, ""
