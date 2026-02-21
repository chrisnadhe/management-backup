from fastapi import APIRouter, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, col, func
from app.database import SessionDep
from app.models import BackupLog, Device, DeviceGroup, Command, Schedule
from app.services.backup_service import run_backup, run_backup_group
import os

router = APIRouter(prefix="/backups", tags=["backups"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_backups(
    request: Request, 
    session: Session = SessionDep,
    q: str = "",
    page: int = 1,
    limit: int = 20
):
    offset = (page - 1) * limit
    
    # Base query
    statement = select(BackupLog).join(Device, isouter=True)
    
    # Filtering
    if q:
        # Search by device hostname, status, or log output
        statement = statement.where(
            (col(Device.hostname).contains(q)) | 
            (col(BackupLog.status).contains(q)) |
            (col(BackupLog.log_output).contains(q))
        )
    
    # Total count for pagination
    total_count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    
    # Pagination and sorting
    statement = statement.order_by(BackupLog.timestamp.desc()).offset(offset).limit(limit)
    backups = session.exec(statement).all()
    
    devices = session.exec(select(Device)).all()
    commands = session.exec(select(Command)).all()
    
    total_pages = (total_count + limit - 1) // limit
    
    return templates.TemplateResponse("backups.html", {
        "request": request, 
        "backups": backups, 
        "devices": devices, 
        "commands": commands,
        "q": q,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count
    })

@router.post("/run/group/{group_id}", response_class=RedirectResponse)
async def trigger_group_backup(
    group_id: int,
    background_tasks: BackgroundTasks,
    command_id: int = Form(None),
    session: Session = SessionDep
):
    group = session.get(DeviceGroup, group_id)
    if not group:
         return RedirectResponse(url="/groups?error=Group not found", status_code=303)

    # Create pending logs for all devices
    from datetime import datetime
    log_map = {}
    if group.devices:
        for device in group.devices:
            backup_log = BackupLog(
                device_id=device.id,
                status="running",
                timestamp=datetime.now(),
                log_output="Backup queued (Group)...",
                file_path=None,
                session_log_path=None
            )
            session.add(backup_log)
            session.commit()
            session.refresh(backup_log)
            log_map[device.id] = backup_log.id

    background_tasks.add_task(run_backup_group, group_id, log_map, command_id)
    return RedirectResponse(url=f"/backups?msg=Group backup started for {group.name}", status_code=303)

@router.post("/run/{device_id}", response_class=RedirectResponse)
async def trigger_backup(
    device_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    command_id: int = Form(None),
    session: Session = SessionDep
):
    device = session.get(Device, device_id)
    if not device:
         return RedirectResponse(url="/backups?error=Device not found", status_code=303)

    # Create pending log
    from datetime import datetime
    backup_log = BackupLog(
        device_id=device_id,
        status="running",
        timestamp=datetime.now(),
        log_output="Backup queued...",
        file_path=None,
        session_log_path=None
    )
    session.add(backup_log)
    session.commit()
    session.refresh(backup_log)

    background_tasks.add_task(run_backup, device_id, backup_log.id, command_id)
    
    return RedirectResponse(url=f"/backups?msg=Backup started for {device.hostname}", status_code=303)

@router.get("/download/{log_id}")
async def download_backup(log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if log and log.file_path:
        return FileResponse(log.file_path, filename=os.path.basename(log.file_path))
    return {"error": "File not found"}
