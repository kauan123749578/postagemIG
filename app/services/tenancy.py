from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from app.models import Account, AdminUser

_tenant_user: ContextVar[AdminUser | None] = ContextVar("tenant_user", default=None)


def set_current_user(user: AdminUser | None) -> None:
    _tenant_user.set(user)


def get_current_user() -> AdminUser | None:
    return _tenant_user.get()


def is_owner(user: AdminUser | None = None) -> bool:
    user = user or get_current_user()
    return user is not None and user.role == "owner"


def scope_accounts(db: Session, query: Query | None = None) -> Query:
    q = query or db.query(Account)
    user = get_current_user()
    if user and user.role != "owner":
        q = q.filter(Account.owner_user_id == user.id)
    return q


def scoped_account_ids(db: Session) -> list[int]:
    return [row[0] for row in scope_accounts(db, db.query(Account.id)).all()]


def get_account_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Conta não encontrada")
    user = get_current_user()
    if user and user.role != "owner" and account.owner_user_id != user.id:
        raise HTTPException(404, "Conta não encontrada")
    return account


def assign_account_owner(account: Account, user: AdminUser) -> None:
    account.owner_user_id = user.id
