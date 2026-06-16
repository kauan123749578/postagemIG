import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import APP_BASE_URL, IMAGES_DIR, VIDEOS_DIR
from app.database import Base, SessionLocal, engine, get_db, migrate_schema
from app.services.db_recovery import LAST_RECOVERY, recover_sqlite_to_postgres, sqlite_backup_info
from app.models import AdminUser
from app.models import Account, LoopConfig, PostLog, RecurringBatchConfig, ScheduledBatch, ScheduledPost
from app.services.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_user,
    delete_user,
    ensure_admin,
    get_session_user,
    list_users,
    login as auth_login,
    logout as auth_logout,
    require_owner,
    set_session_cookie,
)
from app.services.cover import require_batch_cover
from app.services.health import check_account_health, refresh_account_insights
from app.services.instagram import INSTAGRAM_CAPTION_MAX, InstagramAPIError, client_from_account
from app.services.loop_worker import start_loop_worker
from app.services.publisher import publish_reel
from app.services.recurring_batch_worker import kick_recurring_batch, start_recurring_batch_worker
from app.services.schedule_worker import start_schedule_worker
from app.services.media_storage import list_media, save_image, save_video
from app.services.rate_limit import can_post, usage_stats
from app.services.storage import get_storage_status
from app.services.meta_throttle import get_status as meta_throttle_status
from app.services.video_list import normalize_video_payload, video_urls
from app.services import settings as app_settings
from app.services.tenancy import (
    assign_account_owner,
    get_account_or_404,
    scope_accounts,
    scoped_account_ids,
    set_current_user,
)

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PUBLIC_PREFIXES = ("/static", "/media", "/login", "/api/auth/login", "/api/health")


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    db = SessionLocal()
    recovery = {"recovered": False}
    try:
        recovery = recover_sqlite_to_postgres(db)
        if recovery.get("recovered"):
            logging.info("Dados recuperados do SQLite: %s", recovery)
        ensure_admin(db)
    finally:
        db.close()
    app.state.db_recovery = recovery
    start_loop_worker()
    start_schedule_worker()
    start_recurring_batch_worker()
    yield


app = FastAPI(title="Postagem IG Panel", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/media/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="media_videos")
app.mount("/media/images", StaticFiles(directory=str(IMAGES_DIR)), name="media_images")


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if os.getenv("ENV", "production") == "production":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    path = request.url.path
    if _is_public(path):
        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response

    token = request.cookies.get(SESSION_COOKIE)
    db = SessionLocal()
    try:
        user = get_session_user(db, token)
    finally:
        db.close()

    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Não autenticado"}, status_code=401, headers=headers)
        return RedirectResponse("/login", status_code=302, headers=headers)

    if path in ("/settings", "/users", "/api/recovery/sqlite") and user.role != "owner":
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Acesso negado"}, status_code=403, headers=headers)
        return RedirectResponse("/", status_code=302, headers=headers)

    set_current_user(user)
    try:
        response = await call_next(request)
    finally:
        set_current_user(None)
    for k, v in headers.items():
        response.headers[k] = v
    return response


# --- Schemas ---

class AccountCreate(BaseModel):
    name: str
    ig_user_id: str
    access_token: str
    username: str = ""
    proxy_url: str = ""
    graph_api_version: str = "v21.0"
    graph_host: str = "graph.facebook.com"
    max_posts_per_day: int = Field(default=0, ge=0, le=500)
    max_posts_per_hour: int = Field(default=0, ge=0, le=100)
    default_caption: str = ""
    is_active: bool = True
    fallback_account_id: int | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    username: str | None = None
    ig_user_id: str | None = None
    access_token: str | None = None
    proxy_url: str | None = None
    graph_api_version: str | None = None
    graph_host: str | None = None
    max_posts_per_day: int | None = Field(default=None, ge=0, le=500)
    max_posts_per_hour: int | None = Field(default=None, ge=0, le=100)
    default_caption: str | None = None
    is_active: bool | None = None
    fallback_account_id: int | None = None


class PostImageRequest(BaseModel):
    account_id: int
    image_url: str
    caption: str = ""


class PostReelRequest(BaseModel):
    account_id: int
    video_url: str
    caption: str = ""
    cover_url: str = ""
    audio_name: str = ""


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=128)


class PostCarouselRequest(BaseModel):
    account_id: int
    urls: list[str]
    caption: str = ""


class LoopVideoItem(BaseModel):
    video_url: str
    cover_url: str = ""


class LoopConfigRequest(BaseModel):
    videos: list[LoopVideoItem]
    caption: str = ""
    batch_size: int = Field(default=4, ge=1, le=50)
    interval_seconds: int = Field(default=60, ge=0, le=3600)
    batch_cover_url: str = ""


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PostStoryRequest(BaseModel):
    account_id: int
    image_url: str = ""
    video_url: str = ""


class AppSettingsUpdate(BaseModel):
    default_max_posts_per_day: int = Field(ge=0, le=500)
    default_max_posts_per_hour: int = Field(ge=0, le=100)
    default_loop_batch_size: int = Field(ge=1, le=50)
    default_loop_interval_seconds: int = Field(ge=0, le=3600)


class ScheduleItemCreate(BaseModel):
    video_url: str
    cover_url: str = ""
    caption: str = ""
    scheduled_at: str


class ScheduleBatchCreate(BaseModel):
    name: str
    account_id: int
    cover_url: str = ""
    items: list[ScheduleItemCreate] = []
    start_at: str | None = None
    interval_minutes: int = Field(default=60, ge=1, le=1440)
    videos: list[LoopVideoItem] = []
    caption: str = ""


class ContingencyMapping(BaseModel):
    account_id: int
    fallback_account_id: int | None = None


class ContingencyUpdate(BaseModel):
    mappings: list[ContingencyMapping]


class RecurringBatchRequest(BaseModel):
    name: str = "Lote recorrente"
    videos: list[LoopVideoItem]
    caption: str = ""
    cover_url: str = ""
    duration_hours: int = Field(default=12, ge=1, le=168)
    cycle_interval_hours: int = Field(default=1, ge=1, le=24)
    video_interval_seconds: int = Field(default=60, ge=0, le=3600)


class RecurringBatchStart(BaseModel):
    duration_hours: int | None = Field(default=None, ge=1, le=168)


# --- Helpers ---

def _require_cover_url(cover_url: str | None, *, context: str = "lote") -> str:
    try:
        return require_batch_cover(cover_url, context=context)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _account_dict(account: Account, db: Session) -> dict:
    stats = usage_stats(db, account.id, account.max_posts_per_day, account.max_posts_per_hour)
    loop = account.loop_config
    return {
        "id": account.id,
        "name": account.name,
        "username": account.username,
        "ig_user_id": account.ig_user_id,
        "proxy_url": account.proxy_url,
        "max_posts_per_day": account.max_posts_per_day,
        "max_posts_per_hour": account.max_posts_per_hour,
        "default_caption": account.default_caption,
        "is_active": account.is_active,
        "health_status": account.health_status,
        "health_message": account.health_message,
        "profile_views": account.profile_views,
        "total_reach": account.total_reach,
        "total_impressions": account.total_impressions,
        "usage": stats,
        "loop_running": bool(loop and loop.is_running),
        "loop_posts": loop.total_posts if loop else 0,
        "loop_batches": loop.batches_completed if loop else 0,
        "fallback_account_id": account.fallback_account_id,
    }


def _scope_by_accounts(query, column, db: Session):
    ids = scoped_account_ids(db)
    if ids is not None:
        return query.filter(column.in_(ids))
    return query


def _current_user(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    user = get_session_user(db, request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(401, "Não autenticado")
    return user


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _schedule_dict(item: ScheduledPost, db: Session) -> dict:
    account = db.get(Account, item.account_id)
    posted = db.get(Account, item.posted_account_id) if item.posted_account_id else None
    fallback = db.get(Account, item.fallback_account_id) if item.fallback_account_id else None
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "account_id": item.account_id,
        "account_name": account.name if account else "",
        "fallback_account_id": item.fallback_account_id,
        "fallback_name": fallback.name if fallback else "",
        "posted_account_name": posted.name if posted else "",
        "video_url": item.video_url,
        "cover_url": item.cover_url,
        "caption": item.caption,
        "media_type": item.media_type,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
        "status": item.status,
        "error_message": item.error_message,
        "media_id": item.media_id,
        "posted_at": item.posted_at.isoformat() if item.posted_at else None,
        "sort_order": item.sort_order,
    }


_get_account_or_404 = get_account_or_404


def _enforce_post_limits(db: Session, account: Account) -> None:
    allowed, reason = can_post(db, account.id, account.max_posts_per_day, account.max_posts_per_hour)
    if not allowed:
        raise HTTPException(429, reason)


# --- Auth ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    db = SessionLocal()
    try:
        if get_session_user(db, token):
            return RedirectResponse("/", status_code=302)
    finally:
        db.close()
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/api/auth/login")
def api_login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    token = auth_login(db, request, body.username, body.password)
    set_session_cookie(response, token)
    return {"ok": True}


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth_logout(db, request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
    return {"ok": True}


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"page": "dashboard"})


@app.get("/publish", response_class=HTMLResponse)
def publish_page(request: Request):
    return templates.TemplateResponse(request, "publish.html", {"page": "publish"})


@app.get("/schedule", response_class=HTMLResponse)
def schedule_page(request: Request):
    return templates.TemplateResponse(request, "schedule.html", {"page": "schedule"})


@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request):
    return templates.TemplateResponse(request, "accounts.html", {"page": "accounts"})


@app.get("/contingency", response_class=HTMLResponse)
def contingency_page(request: Request):
    return templates.TemplateResponse(request, "contingency.html", {"page": "contingency"})


@app.get("/loop", response_class=HTMLResponse)
def loop_page(request: Request):
    return templates.TemplateResponse(request, "loop.html", {"page": "loop"})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", {"page": "settings"})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, user: AdminUser = Depends(_current_user)):
    require_owner(user)
    return templates.TemplateResponse(request, "users.html", {"page": "users"})


@app.get("/media", response_class=HTMLResponse)
def media_page(request: Request):
    return templates.TemplateResponse(request, "media.html", {"page": "media"})


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    storage = get_storage_status(db)
    return {
        "status": "ok",
        "base_url": APP_BASE_URL,
        "storage": storage,
        "recovery": LAST_RECOVERY,
        "meta_throttle": meta_throttle_status(),
    }


@app.get("/api/storage")
def storage_status(db: Session = Depends(get_db)):
    return {**get_storage_status(db), "recovery": LAST_RECOVERY}


@app.post("/api/recovery/sqlite")
def run_sqlite_recovery(db: Session = Depends(get_db)):
    result = recover_sqlite_to_postgres(db)
    if result.get("recovered"):
        return {"ok": True, **result, "storage": get_storage_status(db)}
    raise HTTPException(400, result.get("error") or result.get("reason", "Não foi possível recuperar"))


@app.get("/api/me")
def api_me(user: AdminUser = Depends(_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/api/users")
def api_list_users(db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    require_owner(user)
    return [
        {"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active, "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in list_users(db)
    ]


@app.post("/api/users", status_code=201)
def api_create_user(body: UserCreateRequest, db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    require_owner(user)
    created = create_user(db, body.username, body.password)
    return {"id": created.id, "username": created.username, "role": created.role}


@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    require_owner(user)
    delete_user(db, user_id, user)
    return {"ok": True}


# --- API: Upload ---

@app.get("/api/uploads")
def get_uploads():
    return list_media()


@app.post("/api/upload/video")
async def upload_video(file: UploadFile = File(...)):
    return save_video(file)


@app.post("/api/upload/videos")
async def upload_videos(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")
    return {"uploaded": [save_video(f) for f in files]}


@app.post("/api/upload/image")
async def upload_image(file: UploadFile = File(...)):
    return save_image(file)


# --- API: Settings ---

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    require_owner(user)
    return {
        **app_settings.get_all_settings(db),
        "caption_max_length": INSTAGRAM_CAPTION_MAX,
        "current_accounts": scope_accounts(db).count(),
        "app_base_url": APP_BASE_URL,
    }


@app.put("/api/settings")
def update_settings(body: AppSettingsUpdate, db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    require_owner(user)
    app_settings.set_setting(db, "default_max_posts_per_day", str(body.default_max_posts_per_day))
    app_settings.set_setting(db, "default_max_posts_per_hour", str(body.default_max_posts_per_hour))
    app_settings.set_setting(db, "default_loop_batch_size", str(body.default_loop_batch_size))
    app_settings.set_setting(db, "default_loop_interval_seconds", str(body.default_loop_interval_seconds))
    db.commit()
    return app_settings.get_all_settings(db)


# --- API: Accounts ---

@app.get("/api/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = scope_accounts(db).order_by(Account.id).all()
    return [_account_dict(a, db) for a in accounts]


@app.post("/api/accounts", status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db), user: AdminUser = Depends(_current_user)):
    ok, reason = app_settings.can_add_account(db)
    if not ok:
        raise HTTPException(400, reason)

    if body.fallback_account_id:
        _get_account_or_404(db, body.fallback_account_id)

    defaults = app_settings.get_all_settings(db)
    account = Account(
        name=body.name,
        username=body.username,
        ig_user_id=body.ig_user_id,
        access_token=body.access_token,
        proxy_url=body.proxy_url,
        graph_api_version=body.graph_api_version,
        graph_host=body.graph_host,
        max_posts_per_day=body.max_posts_per_day if body.max_posts_per_day is not None else int(defaults["default_max_posts_per_day"]),
        max_posts_per_hour=body.max_posts_per_hour if body.max_posts_per_hour is not None else int(defaults["default_max_posts_per_hour"]),
        default_caption=body.default_caption[:INSTAGRAM_CAPTION_MAX],
        is_active=body.is_active,
        fallback_account_id=body.fallback_account_id,
    )
    assign_account_owner(account, user)
    db.add(account)
    db.commit()
    db.refresh(account)
    check_account_health(db, account)
    db.commit()
    return _account_dict(account, db)


@app.get("/api/accounts/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    return _account_dict(_get_account_or_404(db, account_id), db)


@app.get("/api/contingency")
def list_contingency(db: Session = Depends(get_db)):
    accounts = scope_accounts(db).order_by(Account.id).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "username": a.username,
            "is_active": a.is_active,
            "health_status": a.health_status,
            "fallback_account_id": a.fallback_account_id,
            "fallback_name": next((x.name for x in accounts if x.id == a.fallback_account_id), ""),
        }
        for a in accounts
    ]


@app.put("/api/contingency")
def update_contingency(body: ContingencyUpdate, db: Session = Depends(get_db)):
    account_ids = {a.id for a in scope_accounts(db).all()}
    for item in body.mappings:
        if item.account_id not in account_ids:
            raise HTTPException(404, f"Conta {item.account_id} não encontrada")
        if item.fallback_account_id == item.account_id:
            raise HTTPException(400, "Conta não pode ser contingência de si mesma")
        if item.fallback_account_id and item.fallback_account_id not in account_ids:
            raise HTTPException(404, f"Contingência {item.fallback_account_id} não encontrada")

    for item in body.mappings:
        account = db.get(Account, item.account_id)
        if account:
            account.fallback_account_id = item.fallback_account_id
    db.commit()
    return list_contingency(db)


@app.patch("/api/accounts/{account_id}")
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("fallback_account_id"):
        _get_account_or_404(db, data["fallback_account_id"])
    if "default_caption" in data and data["default_caption"] is not None:
        data["default_caption"] = data["default_caption"][:INSTAGRAM_CAPTION_MAX]
    for key, value in data.items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return _account_dict(account, db)


def _purge_account_dependencies(db: Session, account_id: int) -> None:
    db.query(Account).filter(Account.fallback_account_id == account_id).update(
        {Account.fallback_account_id: None}, synchronize_session=False
    )

    recurring = (
        db.query(RecurringBatchConfig)
        .filter(RecurringBatchConfig.account_id == account_id)
        .first()
    )
    if recurring:
        db.delete(recurring)
    db.query(RecurringBatchConfig).filter(RecurringBatchConfig.fallback_account_id == account_id).update(
        {RecurringBatchConfig.fallback_account_id: None}, synchronize_session=False
    )

    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if loop:
        db.delete(loop)

    for batch in db.query(ScheduledBatch).filter(ScheduledBatch.account_id == account_id).all():
        db.query(ScheduledPost).filter(ScheduledPost.batch_id == batch.id).delete()
        db.delete(batch)
    db.query(ScheduledBatch).filter(ScheduledBatch.fallback_account_id == account_id).update(
        {ScheduledBatch.fallback_account_id: None}, synchronize_session=False
    )

    db.query(ScheduledPost).filter(ScheduledPost.account_id == account_id).delete()
    db.query(ScheduledPost).filter(ScheduledPost.fallback_account_id == account_id).update(
        {ScheduledPost.fallback_account_id: None}, synchronize_session=False
    )
    db.query(ScheduledPost).filter(ScheduledPost.posted_account_id == account_id).update(
        {ScheduledPost.posted_account_id: None}, synchronize_session=False
    )

    db.query(PostLog).filter(PostLog.account_id == account_id).delete()


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    _purge_account_dependencies(db, account_id)
    db.delete(account)
    db.commit()
    return {"ok": True}


@app.get("/api/accounts/{account_id}/health")
def account_health(account_id: int, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    result = check_account_health(db, account)
    db.commit()
    return result


@app.get("/api/accounts/{account_id}/insights")
def account_insights(account_id: int, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    return refresh_account_insights(db, account)


@app.get("/api/accounts/{account_id}/posts")
def account_posts(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)
    logs = (
        db.query(PostLog)
        .filter(PostLog.account_id == account_id)
        .order_by(PostLog.posted_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": log.id,
            "media_id": log.media_id,
            "media_type": log.media_type,
            "status": log.status,
            "error_message": log.error_message,
            "views": log.views,
            "impressions": log.impressions,
            "posted_at": log.posted_at.isoformat() if log.posted_at else None,
        }
        for log in logs
    ]


# --- API: Posts ---

@app.post("/api/posts/image")
def post_image(body: PostImageRequest, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, body.account_id)
    _enforce_post_limits(db, account)
    caption = body.caption or account.default_caption
    try:
        media_id = client_from_account(account).post_image(body.image_url, caption)
        db.add(PostLog(account_id=account.id, media_id=media_id, media_type="image", caption_preview=caption[:200], status="success"))
        db.commit()
        return {"media_id": media_id}
    except InstagramAPIError as exc:
        db.add(PostLog(account_id=account.id, media_type="image", status="error", error_message=str(exc)))
        db.commit()
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/posts/reel")
def post_reel(body: PostReelRequest, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, body.account_id)
    _enforce_post_limits(db, account)
    caption = body.caption or account.default_caption
    if not (body.cover_url or "").strip():
        raise HTTPException(400, "Capa é obrigatória para publicar Reels")
    try:
        result = publish_reel(
            db, account, body.video_url, caption,
            cover_url=body.cover_url,
            audio_name=body.audio_name or None,
        )
        return result
    except InstagramAPIError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/posts/story")
def post_story(body: PostStoryRequest, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, body.account_id)
    _enforce_post_limits(db, account)
    if not body.image_url and not body.video_url:
        raise HTTPException(400, "Envie uma imagem ou vídeo para o Story")
    try:
        media_id = client_from_account(account).post_story(
            image_url=body.image_url or None,
            video_url=body.video_url or None,
        )
        db.add(PostLog(account_id=account.id, media_id=media_id, media_type="story", status="success"))
        db.commit()
        return {"media_id": media_id}
    except InstagramAPIError as exc:
        db.add(PostLog(account_id=account.id, media_type="story", status="error", error_message=str(exc)))
        db.commit()
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/posts/carousel")
def post_carousel(body: PostCarouselRequest, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, body.account_id)
    _enforce_post_limits(db, account)
    if not 2 <= len(body.urls) <= 10:
        raise HTTPException(400, "Carrossel precisa de 2 a 10 itens")
    caption = body.caption or account.default_caption
    try:
        media_id = client_from_account(account).post_carousel(body.urls, caption)
        db.add(PostLog(account_id=account.id, media_id=media_id, media_type="carousel", caption_preview=caption[:200], status="success"))
        db.commit()
        return {"media_id": media_id}
    except InstagramAPIError as exc:
        db.add(PostLog(account_id=account.id, media_type="carousel", status="error", error_message=str(exc)))
        db.commit()
        raise HTTPException(400, str(exc)) from exc


# --- API: Loop ---

@app.get("/api/loop/{account_id}")
def get_loop(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)
    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if not loop:
        return {"account_id": account_id, "videos": [], "caption": "", "batch_size": 4, "interval_seconds": 60, "batch_cover_url": "", "is_running": False, "current_index": 0, "batches_completed": 0, "total_posts": 0, "last_error": ""}
    return {
        "account_id": account_id,
        "videos": json.loads(loop.videos_json or "[]"),
        "caption": loop.caption,
        "batch_size": loop.batch_size,
        "interval_seconds": loop.interval_seconds,
        "batch_cover_url": loop.batch_cover_url or "",
        "is_running": loop.is_running,
        "current_index": loop.current_index,
        "batches_completed": loop.batches_completed,
        "total_posts": loop.total_posts,
        "last_error": loop.last_error,
    }


@app.put("/api/loop/{account_id}")
def save_loop(account_id: int, body: LoopConfigRequest, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)

    normalized = normalize_video_payload(body.videos)
    if not normalized:
        loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
        if loop and loop.is_running:
            raise HTTPException(400, "Pare o loop antes de remover todos os vídeos")
        if not loop:
            loop = LoopConfig(account_id=account_id)
            db.add(loop)
        loop.videos_json = "[]"
        loop.current_index = 0
        loop.caption = body.caption[:INSTAGRAM_CAPTION_MAX]
        loop.batch_size = body.batch_size
        loop.interval_seconds = body.interval_seconds
        loop.batch_cover_url = body.batch_cover_url or ""
        db.commit()
        return get_loop(account_id, db)

    videos_json = json.dumps(normalized)
    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if not loop:
        loop = LoopConfig(account_id=account_id)
        db.add(loop)

    if video_urls(loop.videos_json) != [v["video_url"] for v in normalized]:
        loop.current_index = 0

    loop.videos_json = videos_json
    loop.caption = body.caption[:INSTAGRAM_CAPTION_MAX]
    loop.batch_size = body.batch_size
    loop.interval_seconds = body.interval_seconds
    loop.batch_cover_url = body.batch_cover_url or ""
    db.commit()
    return get_loop(account_id, db)


@app.post("/api/loop/{account_id}/start")
def start_loop(account_id: int, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if not loop or not json.loads(loop.videos_json or "[]"):
        raise HTTPException(400, "Configure os vídeos antes de iniciar")
    if not (loop.batch_cover_url or "").strip():
        raise HTTPException(400, "Capa do lote é obrigatória — faça upload da capa antes de iniciar")
    loop.is_running = True
    loop.last_error = ""
    db.commit()
    return {"is_running": True, "message": "Loop contínuo iniciado — não para após lotes"}


@app.post("/api/loop/{account_id}/stop")
def stop_loop(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)
    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if loop:
        loop.is_running = False
        db.commit()
    return {"is_running": False}


def _recurring_dict(config: RecurringBatchConfig, db: Session) -> dict:
    now = datetime.now(timezone.utc)
    ends_at = _normalize_recurring_dt(config.ends_at)
    started_at = _normalize_recurring_dt(config.started_at)
    remaining = None
    if config.is_running and ends_at:
        remaining = max(0, int((ends_at - now).total_seconds() // 60))

    account = db.get(Account, config.account_id)
    videos = json.loads(config.videos_json or "[]")
    video_count = len(videos)
    cycle_index = config.cycle_video_index or 0
    posts_in_cycle = cycle_index if video_count else 0
    cycle_progress = int((posts_in_cycle / video_count) * 100) if video_count else 0

    next_cycle_at = None
    waiting_for_cycle = False
    if config.is_running and cycle_index == 0 and config.last_cycle_at:
        last_cycle = _normalize_recurring_dt(config.last_cycle_at)
        if last_cycle:
            next_cycle_at = last_cycle + timedelta(hours=config.cycle_interval_hours)
            waiting_for_cycle = now < next_cycle_at

    next_post_at = None
    waiting_for_video = False
    next_retry_at = None
    consecutive_failures = config.consecutive_failures or 0
    if config.is_running and not waiting_for_cycle:
        last_event = _normalize_recurring_dt(config.last_attempt_at) or _normalize_recurring_dt(config.last_post_at)
        is_retry = consecutive_failures > 0
        if last_event and (cycle_index > 0 or is_retry):
            base_wait = config.video_interval_seconds or 0
            if is_retry:
                base_wait = max(base_wait, 120)
            if base_wait > 0:
                next_post_at = last_event + timedelta(seconds=base_wait)
                next_retry_at = next_post_at
                waiting_for_video = now < next_post_at

    usage = {}
    if account:
        usage = usage_stats(db, account.id, account.max_posts_per_day, account.max_posts_per_hour)

    current_video_label = ""
    if video_count and config.is_running:
        if waiting_for_cycle:
            current_video_label = f"Aguardando próximo ciclo (lote completo: {video_count} vídeos)"
        elif cycle_index < video_count:
            current_video_label = f"Próximo: vídeo {cycle_index + 1} de {video_count}"
        else:
            current_video_label = f"Ciclo concluído — {video_count} vídeos"

    status_label = "rodando"
    if not config.is_running:
        status_label = "parado"
    elif waiting_for_cycle:
        status_label = "aguardando_ciclo"
    elif waiting_for_video:
        status_label = "aguardando_intervalo"
    elif config.last_error and config.last_error.startswith("Aguardando limite"):
        status_label = "limite_api"
    elif consecutive_failures > 0:
        status_label = "erro_video"

    return {
        "id": config.id,
        "account_id": config.account_id,
        "account_name": account.name if account else "",
        "account_username": account.username if account else "",
        "name": config.name,
        "videos": videos,
        "video_count": video_count,
        "caption": config.caption,
        "fallback_account_id": config.fallback_account_id,
        "cover_url": config.cover_url or "",
        "duration_hours": config.duration_hours,
        "cycle_interval_hours": config.cycle_interval_hours,
        "video_interval_seconds": config.video_interval_seconds,
        "is_running": config.is_running,
        "status_label": status_label,
        "started_at": started_at.isoformat() if started_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
        "last_post_at": config.last_post_at.isoformat() if config.last_post_at else None,
        "last_cycle_at": config.last_cycle_at.isoformat() if config.last_cycle_at else None,
        "cycles_completed": config.cycles_completed,
        "total_posts": config.total_posts,
        "cycle_video_index": cycle_index,
        "posts_in_current_cycle": posts_in_cycle,
        "cycle_progress_percent": cycle_progress,
        "current_video_label": current_video_label,
        "next_cycle_at": next_cycle_at.isoformat() if next_cycle_at else None,
        "next_post_at": next_post_at.isoformat() if next_post_at else None,
        "waiting_for_cycle": waiting_for_cycle,
        "waiting_for_video": waiting_for_video,
        "consecutive_failures": consecutive_failures,
        "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
        "last_error": config.last_error,
        "remaining_minutes": remaining,
        "usage": usage,
    }


def _normalize_recurring_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# --- API: Recurring Batch ---

@app.get("/api/recurring-batches/active")
def list_active_recurring_batches(db: Session = Depends(get_db)):
    configs = (
        _scope_by_accounts(db.query(RecurringBatchConfig), RecurringBatchConfig.account_id, db)
        .filter(RecurringBatchConfig.is_running.is_(True))
        .order_by(RecurringBatchConfig.started_at.desc())
        .all()
    )
    return [_recurring_dict(c, db) for c in configs]


@app.get("/api/recurring-batches")
def list_recurring_batches(db: Session = Depends(get_db)):
    configs = _scope_by_accounts(db.query(RecurringBatchConfig), RecurringBatchConfig.account_id, db).order_by(RecurringBatchConfig.account_id).all()
    return [_recurring_dict(c, db) for c in configs if json.loads(c.videos_json or "[]")]


@app.get("/api/recurring-batch/{account_id}")
def get_recurring_batch(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)
    config = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.account_id == account_id).first()
    if not config:
        return {
            "account_id": account_id,
            "name": "Lote recorrente",
            "videos": [],
            "caption": "",
            "duration_hours": 12,
            "cycle_interval_hours": 1,
            "video_interval_seconds": 60,
            "is_running": False,
            "cycles_completed": 0,
            "total_posts": 0,
            "last_error": "",
        }
    return _recurring_dict(config, db)


@app.put("/api/recurring-batch/{account_id}")
def save_recurring_batch(account_id: int, body: RecurringBatchRequest, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)

    config = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.account_id == account_id).first()
    if not config:
        config = RecurringBatchConfig(account_id=account_id)
        db.add(config)

    normalized = normalize_video_payload(body.videos)
    if not normalized:
        if config.is_running:
            raise HTTPException(400, "Pare o lote recorrente antes de remover todos os vídeos")
        config.name = body.name
        config.videos_json = "[]"
        config.caption = body.caption[:INSTAGRAM_CAPTION_MAX]
        config.cover_url = body.cover_url or ""
        config.duration_hours = body.duration_hours
        config.cycle_interval_hours = body.cycle_interval_hours
        config.video_interval_seconds = body.video_interval_seconds
        config.cycle_video_index = 0
        config.consecutive_failures = 0
        db.commit()
        return _recurring_dict(config, db)

    if video_urls(config.videos_json) != [v["video_url"] for v in normalized]:
        config.cycle_video_index = 0
        config.consecutive_failures = 0

    config.name = body.name
    config.videos_json = json.dumps(normalized)
    config.caption = body.caption[:INSTAGRAM_CAPTION_MAX]
    config.cover_url = body.cover_url or ""
    config.duration_hours = body.duration_hours
    config.cycle_interval_hours = body.cycle_interval_hours
    config.video_interval_seconds = body.video_interval_seconds
    if config.is_running and config.cycle_video_index >= len(normalized):
        config.cycle_video_index = 0
    db.commit()
    return _recurring_dict(config, db)


@app.post("/api/recurring-batch/{account_id}/start")
def start_recurring_batch(account_id: int, body: RecurringBatchStart, db: Session = Depends(get_db)):
    account = _get_account_or_404(db, account_id)
    config = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.account_id == account_id).first()
    if not config or not json.loads(config.videos_json or "[]"):
        raise HTTPException(400, "Configure os vídeos do lote antes de iniciar")
    if not (config.cover_url or "").strip():
        raise HTTPException(400, "Capa do lote é obrigatória — faça upload da capa antes de iniciar")

    loop = db.query(LoopConfig).filter(LoopConfig.account_id == account_id).first()
    if loop and loop.is_running:
        loop.is_running = False

    duration = body.duration_hours or config.duration_hours
    now = datetime.now(timezone.utc)
    config.duration_hours = duration
    config.is_running = True
    config.started_at = now
    config.ends_at = now + timedelta(hours=duration)
    config.cycle_video_index = 0
    config.cycles_completed = 0
    config.total_posts = 0
    config.last_cycle_at = None
    config.last_post_at = None
    config.last_attempt_at = None
    config.consecutive_failures = 0
    config.last_error = ""
    db.commit()
    db.refresh(config)
    kick_recurring_batch(config.id)
    return {
        **_recurring_dict(config, db),
        "message": f"Lote recorrente ativo por {duration}h — primeiro lote agora, depois 1 lote a cada {config.cycle_interval_hours}h",
    }


@app.post("/api/recurring-batch/{account_id}/stop")
def stop_recurring_batch(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(db, account_id)
    config = db.query(RecurringBatchConfig).filter(RecurringBatchConfig.account_id == account_id).first()
    if config:
        config.is_running = False
        config.last_error = "Parado manualmente"
        db.commit()
    return {"is_running": False}


# --- API: Schedule ---

@app.get("/api/schedule")
def list_schedule(db: Session = Depends(get_db)):
    items = (
        _scope_by_accounts(db.query(ScheduledPost), ScheduledPost.account_id, db)
        .order_by(ScheduledPost.scheduled_at.desc())
        .limit(200)
        .all()
    )
    return [_schedule_dict(i, db) for i in items]


@app.post("/api/schedule/batch", status_code=201)
def create_schedule_batch(body: ScheduleBatchCreate, db: Session = Depends(get_db)):
    _get_account_or_404(db, body.account_id)
    batch_cover = _require_cover_url(body.cover_url, context="lote agendado")

    batch = ScheduledBatch(
        name=body.name,
        account_id=body.account_id,
        fallback_account_id=None,
        cover_url=batch_cover,
    )
    db.add(batch)
    db.flush()

    created: list[ScheduledPost] = []

    if body.items:
        for idx, item in enumerate(body.items):
            post = ScheduledPost(
                batch_id=batch.id,
                account_id=body.account_id,
                fallback_account_id=None,
                video_url=item.video_url,
                cover_url=item.cover_url.strip() or batch_cover,
                caption=(item.caption or body.caption)[:INSTAGRAM_CAPTION_MAX],
                scheduled_at=_parse_dt(item.scheduled_at),
                sort_order=idx,
            )
            db.add(post)
            created.append(post)
    elif body.videos and body.start_at:
        start = _parse_dt(body.start_at)
        for idx, video in enumerate(body.videos):
            scheduled = start + timedelta(minutes=body.interval_minutes * idx)
            post = ScheduledPost(
                batch_id=batch.id,
                account_id=body.account_id,
                fallback_account_id=None,
                video_url=video.video_url,
                cover_url=(video.cover_url or "").strip() or batch_cover,
                caption=body.caption[:INSTAGRAM_CAPTION_MAX],
                scheduled_at=scheduled,
                sort_order=idx,
            )
            db.add(post)
            created.append(post)
    else:
        raise HTTPException(400, "Informe items com horários ou videos + start_at")

    db.commit()
    return {"batch_id": batch.id, "created": len(created), "items": [_schedule_dict(p, db) for p in created]}


@app.delete("/api/schedule/{item_id}")
def cancel_schedule(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ScheduledPost, item_id)
    if not item:
        raise HTTPException(404, "Agendamento não encontrado")
    _get_account_or_404(db, item.account_id)
    if item.status not in ("pending", "error"):
        raise HTTPException(400, "Só é possível cancelar pendentes ou com erro")
    item.status = "cancelled"
    db.commit()
    return {"ok": True}


@app.get("/api/recent-posts")
def recent_posts(db: Session = Depends(get_db)):
    logs = (
        _scope_by_accounts(db.query(PostLog), PostLog.account_id, db)
        .order_by(PostLog.posted_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for log in logs:
        acc = db.get(Account, log.account_id)
        result.append({
            "id": log.id,
            "account": acc.name if acc else f"#{log.account_id}",
            "username": acc.username if acc else "",
            "media_type": log.media_type,
            "status": log.status,
            "error_message": log.error_message,
            "caption_preview": log.caption_preview,
            "media_id": log.media_id,
            "posted_at": log.posted_at.isoformat() if log.posted_at else None,
        })
    return result


# --- API: Dashboard ---

@app.get("/api/dashboard")
def dashboard_data(db: Session = Depends(get_db)):
    accounts = scope_accounts(db).all()
    account_ids = scoped_account_ids(db)
    posts_q = db.query(PostLog)
    loops_q = db.query(LoopConfig)
    recurring_q = db.query(RecurringBatchConfig)
    schedule_q = db.query(ScheduledPost)
    if account_ids is not None:
        posts_q = posts_q.filter(PostLog.account_id.in_(account_ids))
        loops_q = loops_q.filter(LoopConfig.account_id.in_(account_ids))
        recurring_q = recurring_q.filter(RecurringBatchConfig.account_id.in_(account_ids))
        schedule_q = schedule_q.filter(ScheduledPost.account_id.in_(account_ids))

    total_posts = posts_q.filter(PostLog.status == "success").count()
    errors = posts_q.filter(PostLog.status == "error").count()
    running_loops = loops_q.filter(LoopConfig.is_running.is_(True)).count()
    running_recurring = recurring_q.filter(RecurringBatchConfig.is_running.is_(True)).count()
    pending_schedule = schedule_q.filter(ScheduledPost.status == "pending").count()
    settings = app_settings.get_all_settings(db)

    now = datetime.now(timezone.utc)
    chart_days = []
    chart_success = []
    chart_errors = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        chart_days.append(day_start.strftime("%d/%m"))
        chart_success.append(
            posts_q.filter(PostLog.status == "success", PostLog.posted_at >= day_start, PostLog.posted_at < day_end)
            .count()
        )
        chart_errors.append(
            posts_q.filter(PostLog.status == "error", PostLog.posted_at >= day_start, PostLog.posted_at < day_end)
            .count()
        )

    schedule_stats = {
        "pending": schedule_q.filter(ScheduledPost.status == "pending").count(),
        "posted": schedule_q.filter(ScheduledPost.status == "posted").count(),
        "error": schedule_q.filter(ScheduledPost.status == "error").count(),
        "processing": schedule_q.filter(ScheduledPost.status == "processing").count(),
    }

    return {
        "total_accounts": len(accounts),
        "total_posts": total_posts,
        "total_errors": errors,
        "running_loops": running_loops,
        "running_recurring": running_recurring,
        "pending_schedule": pending_schedule,
        "app_base_url": APP_BASE_URL,
        "storage": get_storage_status(db),
        "meta_throttle": meta_throttle_status(),
        "accounts": [_account_dict(a, db) for a in accounts],
        "chart": {"labels": chart_days, "success": chart_success, "errors": chart_errors},
        "schedule_stats": schedule_stats,
    }
