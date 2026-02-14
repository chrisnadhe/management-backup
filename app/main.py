from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel
from app.database import engine

# Import models to register them with SQLModel
from app.models import Device, Credential, Command, Schedule, BackupLog

app = FastAPI(title="Network Backup Manager")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
from app.routers import devices, groups, credentials, commands, backups, schedules, logs
from app.services.scheduler_service import start_scheduler

app.include_router(devices.router)
app.include_router(groups.router)
app.include_router(credentials.router)
app.include_router(commands.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(logs.router)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    start_scheduler()


from sqlmodel import select, func, Session
from app.database import SessionDep

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
