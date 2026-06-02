from fastapi import APIRouter, Form, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from sqlmodel import Session, select, col, func
from app.database import SessionDep
from app.models import BackupLog, Device, DeviceGroup, Command
from app.services.backup_service import run_backup, run_backup_group
from app.templates import templates
import os

router = APIRouter(prefix="/backups", tags=["backups"])

# Helper to fetch backups context
def get_backups_context(session: Session, request: Request, q: str = "", page: int = 1, limit: int = 20, view: str = "list"):
    if view == "grouped":
        groups = session.exec(select(DeviceGroup)).all()
        devices = session.exec(select(Device)).all()
        commands = session.exec(select(Command)).all()
        
        grouped_data = []
        for group in groups:
            group_devices_info = []
            group_devices = [d for d in devices if d.group_id == group.id]
            for d in group_devices:
                backups = session.exec(
                    select(BackupLog)
                    .where(BackupLog.device_id == d.id)
                    .order_by(BackupLog.timestamp.desc())
                    .limit(10)
                ).all()
                group_devices_info.append({
                    "device": d,
                    "latest_backups": backups
                })
            
            if group_devices_info:
                grouped_data.append({
                    "group": group,
                    "devices": group_devices_info
                })
        
        unassigned_devices = [d for d in devices if d.group_id is None]
        unassigned_devices_info = []
        for d in unassigned_devices:
            backups = session.exec(
                select(BackupLog)
                .where(BackupLog.device_id == d.id)
                .order_by(BackupLog.timestamp.desc())
                .limit(10)
            ).all()
            unassigned_devices_info.append({
                "device": d,
                "latest_backups": backups
            })
            
        if unassigned_devices_info:
            grouped_data.append({
                "group": {"name": "Unassigned", "description": "Devices not assigned to any group"},
                "devices": unassigned_devices_info
            })
            
        return {
            "request": request,
            "grouped_data": grouped_data,
            "view": view,
            "q": q,
            "page": page,
            "limit": limit,
            "devices": devices,
            "commands": commands
        }

    # Default List view
    offset = (page - 1) * limit
    statement = select(BackupLog).join(Device, isouter=True)
    if q:
        statement = statement.where(
            (col(Device.hostname).contains(q)) | 
            (col(BackupLog.status).contains(q)) |
            (col(BackupLog.log_output).contains(q))
        )
    
    total_count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    statement = statement.order_by(BackupLog.timestamp.desc()).offset(offset).limit(limit)
    backups = session.exec(statement).all()
    
    devices = session.exec(select(Device)).all()
    commands = session.exec(select(Command)).all()
    total_pages = (total_count + limit - 1) // limit
    
    return {
        "request": request, 
        "backups": backups, 
        "devices": devices, 
        "commands": commands,
        "q": q,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count,
        "view": view
    }

@router.get("", response_class=HTMLResponse)
async def list_backups(
    request: Request, 
    session: Session = SessionDep,
    q: str = "",
    page: int = 1,
    limit: int = 20,
    view: str = "list"
):
    context = get_backups_context(session, request, q, page, limit, view)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("backups_table.html", context)
    return templates.TemplateResponse("backups.html", context)

@router.get("/status/{log_id}", response_class=HTMLResponse)
async def get_backup_status(
    log_id: int, 
    view: str = "badge", 
    context: str = "list", 
    session: Session = SessionDep
):
    log = session.get(BackupLog, log_id)
    if not log:
        return HTMLResponse('<span class="text-slate-400">Unknown</span>')
    
    if view == "badge":
        if log.status == "running":
            trigger_attr = f'hx-get="/backups/status/{log_id}?view=badge&context={context}" hx-trigger="every 2s" hx-swap="outerHTML"'
            spinner = '<i class="fas fa-spinner fa-spin mr-1.5 text-amber-500"></i>'
            status_class = "bg-amber-50 text-amber-700 border-amber-200"
        elif log.status == "success":
            trigger_attr = ""
            spinner = '<i class="fas fa-check-circle mr-1.5 text-emerald-500"></i>'
            status_class = "bg-emerald-50 text-emerald-700 border-emerald-200"
        else:
            trigger_attr = ""
            spinner = '<i class="fas fa-times-circle mr-1.5 text-rose-500"></i>'
            status_class = "bg-rose-50 text-rose-700 border-rose-200"
            
        px = "px-2.5 py-0.5 text-xs" if context == "list" else "px-2 py-0.5 text-[10px]"
        html = f"""
        <span class="inline-flex items-center {px} font-bold rounded-full border {status_class}" {trigger_attr}>
            {spinner}{log.status}
        </span>
        """
        return HTMLResponse(html)
        
    elif view == "log":
        log_output = log.log_output or "Running backup command..."
        if log.status == "running":
            trigger_attr = f'hx-get="/backups/status/{log_id}?view=log" hx-trigger="every 2s" hx-swap="outerHTML"'
        else:
            trigger_attr = ""
            
        html = f"""
        <pre id="log-output-content-{log_id}" 
             class="text-xs font-mono whitespace-pre-wrap text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-800 max-h-60 overflow-y-auto"
             {trigger_attr}>{log_output}</pre>
        """
        return HTMLResponse(html)
        
    return HTMLResponse("")

@router.post("/run/group/{group_id}")
async def trigger_group_backup(
    group_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    command_id: int = Form(None),
    session: Session = SessionDep
):
    group = session.get(DeviceGroup, group_id)
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")

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
    msg = f"Group backup started for group {group.name}."
    
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = f'{{"refreshList": "", "showToast": {{"message": "{msg}", "type": "info"}}}}'
        return response
        
    return RedirectResponse(url=f"/backups?msg={msg}", status_code=303)

@router.post("/run/{device_id}")
async def trigger_backup(
    device_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    command_id: int = Form(None),
    session: Session = SessionDep
):
    device = session.get(Device, device_id)
    if not device:
         raise HTTPException(status_code=404, detail="Device not found")

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
    msg = f"Backup started for {device.hostname}."
    
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = f'{{"refreshList": "", "showToast": {{"message": "{msg}", "type": "info"}}}}'
        return response
        
    return RedirectResponse(url=f"/backups?msg={msg}", status_code=303)

@router.get("/download/{log_id}")
async def download_backup(log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if log and log.file_path:
        return FileResponse(log.file_path, filename=os.path.basename(log.file_path))
    return {"error": "File not found"}

@router.get("/download/group/{group_id}")
async def download_group_backups(group_id: int, session: Session = SessionDep):
    import zipfile
    import io
    from datetime import datetime
    
    group = session.get(DeviceGroup, group_id)
    if not group:
        return RedirectResponse(url="/backups?error=Group not found", status_code=303)
        
    devices = group.devices
    if not devices:
        return RedirectResponse(url=f"/backups?error=Group '{group.name}' has no devices.", status_code=303)
        
    # Find the latest successful backup with a configuration file for each device
    backup_files = []
    for device in devices:
        latest_success = session.exec(
            select(BackupLog)
            .where(BackupLog.device_id == device.id)
            .where(BackupLog.status == "success")
            .where(BackupLog.file_path != None)
            .order_by(BackupLog.timestamp.desc())
            .limit(1)
        ).first()
        
        if latest_success and latest_success.file_path and os.path.exists(latest_success.file_path):
            backup_files.append((device.hostname, latest_success.file_path))
            
    if not backup_files:
        return RedirectResponse(
            url=f"/backups?error=No successful configuration backups found for devices in group '{group.name}'.", 
            status_code=303
        )
        
    # Create zip archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for hostname, file_path in backup_files:
            # Save file inside archive named by its device hostname
            arcname = f"{hostname}_{os.path.basename(file_path)}"
            zip_file.write(file_path, arcname=arcname)
            
    zip_buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backups_{group.name}_{timestamp}.zip"
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(zip_buffer, media_type="application/x-zip-compressed", headers=headers)

