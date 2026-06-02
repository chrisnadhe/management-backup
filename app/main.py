from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import SQLModel, select, func, Session

# Logging — aktifkan sebelum import lain
from app.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# Database and Models
from app.database import engine, SessionDep
from app.models import Device, BackupLog, User

# Auth
from app.auth import get_current_user, has_no_users, auth_context, is_admin

# Services
from app.services.scheduler_service import start_scheduler

# Routers
from app.routers import devices, groups, credentials, commands, backups, schedules, logs, push
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.routers import settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    start_scheduler()
    logger.info("Network Backup Manager started")
    yield
    logger.info("Network Backup Manager shutting down...")


# --- App Definition ---
app = FastAPI(title="Network Backup Manager", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
from app.templates import templates

# Include routers
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(settings_router.router)
app.include_router(devices.router)
app.include_router(groups.router)
app.include_router(credentials.router)
app.include_router(commands.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(logs.router)
app.include_router(push.router)


# --- Auth Middleware ---
# Daftar path yang TIDAK perlu login
PUBLIC_PATHS = {"/login", "/logout", "/setup"}
PUBLIC_PREFIXES = ("/static",)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Skip auth untuk path publik
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # Jika belum ada user → redirect ke setup
    if has_no_users():
        return RedirectResponse(url="/setup", status_code=302)

    # Cek session
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = SessionDep):
    total_devices = session.exec(select(func.count(Device.id))).one()
    successful_backups = session.exec(
        select(func.count(BackupLog.id)).where(BackupLog.status == "success")
    ).one()
    failed_backups = session.exec(
        select(func.count(BackupLog.id)).where(BackupLog.status == "failed")
    ).one()
    recent_logs = session.exec(
        select(BackupLog).order_by(BackupLog.timestamp.desc()).limit(5)
    ).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_devices": total_devices,
        "successful_backups": successful_backups,
        "failed_backups": failed_backups,
        "recent_logs": recent_logs,
        **auth_context(request),
    })