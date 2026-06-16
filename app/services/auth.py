import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.models import AdminUser, AuthSession, LoginAttempt

SESSION_COOKIE = "ig_session"
SESSION_HOURS = 12
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15
MIN_PASSWORD_LENGTH = 12

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(f"{SECRET_KEY}:{token}".encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_admin(db: Session) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin").strip()
    password = os.getenv("ADMIN_PASSWORD", "").strip()

    owner = db.query(AdminUser).filter(AdminUser.role == "owner").first()
    if owner:
        if password and len(password) >= MIN_PASSWORD_LENGTH:
            owner.username = username
            owner.password_hash = hash_password(password)
            owner.is_active = True
            db.commit()
            logging.info("Credenciais do admin sincronizadas com variáveis de ambiente")
        return

    if db.query(AdminUser).count() > 0:
        return

    if not password or len(password) < MIN_PASSWORD_LENGTH:
        password = secrets.token_urlsafe(18)
        print(f"[SEGURANÇA] Admin criado — usuário: {username} | senha: {password}")
        print(f"[SEGURANÇA] ADMIN_PASSWORD precisa ter {MIN_PASSWORD_LENGTH}+ caracteres. Veja os logs do deploy.")

    db.add(AdminUser(username=username, password_hash=hash_password(password), role="owner"))
    db.commit()


def create_user(db: Session, username: str, password: str, role: str = "client") -> AdminUser:
    username = username.strip().lower()
    if len(username) < 3:
        raise HTTPException(400, "Usuário deve ter pelo menos 3 caracteres")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")
    if db.query(AdminUser).filter(AdminUser.username == username).first():
        raise HTTPException(400, "Usuário já existe")
    user = AdminUser(username=username, password_hash=hash_password(password), role="client")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[AdminUser]:
    return db.query(AdminUser).order_by(AdminUser.id).all()


def delete_user(db: Session, user_id: int, current_user: AdminUser) -> None:
    target = db.get(AdminUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado")
    if target.id == current_user.id:
        raise HTTPException(400, "Você não pode excluir a si mesmo")
    if target.role == "owner":
        raise HTTPException(400, "Não é possível excluir o proprietário")
    db.delete(target)
    db.commit()


def require_owner(user: AdminUser) -> None:
    if user.role != "owner":
        raise HTTPException(403, "Apenas o administrador principal pode gerenciar usuários")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_rate_limited(db: Session, ip: str) -> bool:
    since = _utcnow() - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    attempts = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.ip_address == ip, LoginAttempt.attempted_at >= since)
        .count()
    )
    return attempts >= LOGIN_MAX_ATTEMPTS


def _record_attempt(db: Session, ip: str, success: bool) -> None:
    db.add(LoginAttempt(ip_address=ip, success=success))
    db.commit()


def login(db: Session, request: Request, username: str, password: str) -> str:
    ip = _client_ip(request)
    if _is_rate_limited(db, ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos.")

    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        _record_attempt(db, ip, False)
        raise HTTPException(401, "Usuário ou senha inválidos")

    _record_attempt(db, ip, True)
    token = secrets.token_urlsafe(48)
    expires = _utcnow() + timedelta(hours=SESSION_HOURS)
    db.add(AuthSession(token_hash=_hash_token(token), user_id=user.id, expires_at=expires, ip_address=ip))
    db.commit()
    return token


def logout(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).first()
    if session:
        db.delete(session)
        db.commit()


def get_session_user(db: Session, token: str | None) -> AdminUser | None:
    if not token:
        return None
    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == _hash_token(token))
        .first()
    )
    if not session:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _utcnow():
        db.delete(session)
        db.commit()
        return None
    return db.get(AdminUser, session.user_id)


def set_session_cookie(response: Response, token: str) -> None:
    secure = os.getenv("ENV", "production") == "production"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
