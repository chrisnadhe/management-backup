from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel, select, func, Session

# Database and Models
from app.database import engine, SessionDep
from app.models import Device, BackupLog

# Services
from app.services.scheduler_service import start_scheduler

# Routers
from app.routers import devices, groups, credentials, commands, backups, schedules, logs

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    SQLModel.metadata.create_all(engine)
    start_scheduler()
    
    yield
    
    # Shutdown logic
    print("Shutting down...")

# --- App Definition ---
app = FastAPI(
    title="Network Backup Manager",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(devices.router)
app.include_router(groups.router)
app.include_router(credentials.router)
app.include_router(commands.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(logs.router)

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = SessionDep):
    # Stats
    total_devices = session.exec(select(func.count(Device.id))).one()
    successful_backups = session.exec(select(func.count(BackupLog.id)).where(BackupLog.status == "success")).one()
    failed_backups = session.exec(select(func.count(BackupLog.id)).where(BackupLog.status == "failed")).one()
    
    # Recent Activity (last 5)
    recent_logs = session.exec(select(BackupLog).order_by(BackupLog.timestamp.desc()).limit(5)).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_devices": total_devices,
        "successful_backups": successful_backups,
        "failed_backups": failed_backups,
        "recent_logs": recent_logs
    })