import difflib
import io
import os
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from sqlmodel import Session, select, col, func

from app.database import SessionDep
from app.logging_config import get_logger
from app.models import BackupLog, Device, DeviceGroup, Command
from app.services.backup_service import run_backup, run_backup_group
from app.templates import templates

logger = get_logger(__name__)
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
                group_devices_info.append({"device": d, "latest_backups": backups})

            if group_devices_info:
                grouped_data.append({"group": group, "devices": group_devices_info})

        unassigned_devices = [d for d in devices if d.group_id is None]
        unassigned_devices_info = []
        for d in unassigned_devices:
            backups = session.exec(
                select(BackupLog)
                .where(BackupLog.device_id == d.id)
                .order_by(BackupLog.timestamp.desc())
                .limit(10)
            ).all()
            unassigned_devices_info.append({"device": d, "latest_backups": backups})

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
    command_id_str: str = Form(None, alias="command_id"),
    session: Session = SessionDep
):
    group = session.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    command_id = int(command_id_str) if command_id_str and command_id_str.isdigit() else None

    log_map = {}
    if group.devices:
        for device in group.devices:
            backup_log = BackupLog(
                device_id=device.id,
                status="running",
                timestamp=datetime.now(timezone.utc),
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
    logger.info(msg)

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
    command_id_str: str = Form(None, alias="command_id"),
    session: Session = SessionDep
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    command_id = int(command_id_str) if command_id_str and command_id_str.isdigit() else None

    backup_log = BackupLog(
        device_id=device_id,
        status="running",
        timestamp=datetime.now(timezone.utc),
        log_output="Backup queued...",
        file_path=None,
        session_log_path=None
    )
    session.add(backup_log)
    session.commit()
    session.refresh(backup_log)

    background_tasks.add_task(run_backup, device_id, backup_log.id, command_id)
    msg = f"Backup started for {device.hostname}."
    logger.info(msg)

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
    group = session.get(DeviceGroup, group_id)
    if not group:
        return RedirectResponse(url="/backups?error=Group not found", status_code=303)

    devices = group.devices
    if not devices:
        return RedirectResponse(url=f"/backups?error=Group '{group.name}' has no devices.", status_code=303)

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

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for hostname, file_path in backup_files:
            arcname = f"{hostname}_{os.path.basename(file_path)}"
            zip_file.write(file_path, arcname=arcname)

    zip_buffer.seek(0)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backups_{group.name}_{timestamp}.zip"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(zip_buffer, media_type="application/x-zip-compressed", headers=headers)


# Preview backup file content
@router.get("/{log_id}/preview", response_class=HTMLResponse)
async def preview_backup(log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if not log or not log.file_path or not os.path.exists(log.file_path):
        return HTMLResponse('<p class="text-slate-400 text-sm">File tidak tersedia.</p>')
    with open(log.file_path, 'r', errors='replace') as f:
        content = f.read()
    # Return modal HTML with pre-formatted content
    import html as html_lib
    html = f'''<div class="space-y-4">
        <div class="flex items-center justify-between">
            <h3 class="text-lg font-bold text-slate-800">Backup Preview</h3>
            <span class="text-xs text-slate-500">{os.path.basename(log.file_path)}</span>
        </div>
        <pre class="text-xs font-mono text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-700 max-h-96 overflow-auto whitespace-pre-wrap break-all">{html_lib.escape(content)}</pre>
        <div class="flex justify-end">
            <a href="/backups/download/{log_id}" class="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700">Download</a>
        </div>
    </div>'''
    return HTMLResponse(html)


# Diff between two backup versions
@router.get("/{log_id}/diff", response_class=HTMLResponse)
async def diff_backup(log_id: int, compare_with: int, session: Session = SessionDep):
    import html as html_lib
    log1 = session.get(BackupLog, log_id)
    log2 = session.get(BackupLog, compare_with)

    if not log1 or not log2:
        return HTMLResponse('<p class="text-red-500 text-sm">Log tidak ditemukan.</p>')

    content1 = ''
    content2 = ''
    if log1.file_path and os.path.exists(log1.file_path):
        with open(log1.file_path, 'r', errors='replace') as f:
            content1 = f.read()
    if log2.file_path and os.path.exists(log2.file_path):
        with open(log2.file_path, 'r', errors='replace') as f:
            content2 = f.read()

    lines1 = content1.splitlines()
    lines2 = content2.splitlines()

    # Generate side-by-side diff rows
    matcher = difflib.SequenceMatcher(None, lines1, lines2)
    rows = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for l in lines1[i1:i2]:
                rows.append(('equal', l, l))
        elif tag == 'replace':
            for l, r in zip(lines1[i1:i2], lines2[j1:j2]):
                rows.append(('replace', l, r))
            for l in lines1[i1+len(lines2[j1:j2]):i2]:
                rows.append(('delete', l, ''))
            for r in lines2[j1+len(lines1[i1:i2]):j2]:
                rows.append(('insert', '', r))
        elif tag == 'delete':
            for l in lines1[i1:i2]:
                rows.append(('delete', l, ''))
        elif tag == 'insert':
            for r in lines2[j1:j2]:
                rows.append(('insert', '', r))

    # Build HTML table
    table_rows = ''
    for tag, left, right in rows:
        if tag == 'equal':
            bg = ''
            left_cls = 'text-slate-400'
            right_cls = 'text-slate-400'
        elif tag == 'replace':
            bg = 'bg-amber-950/40'
            left_cls = 'text-amber-300'
            right_cls = 'text-emerald-300'
        elif tag == 'delete':
            bg = 'bg-rose-950/40'
            left_cls = 'text-rose-300'
            right_cls = ''
        else:  # insert
            bg = 'bg-emerald-950/40'
            left_cls = ''
            right_cls = 'text-emerald-300'

        table_rows += f'<tr class="{bg}"><td class="px-2 py-0.5 font-mono text-xs {left_cls} border-r border-slate-700 w-1/2 whitespace-pre">{html_lib.escape(left)}</td><td class="px-2 py-0.5 font-mono text-xs {right_cls} w-1/2 whitespace-pre">{html_lib.escape(right)}</td></tr>'

    fname1 = os.path.basename(log1.file_path) if log1.file_path else 'N/A'
    fname2 = os.path.basename(log2.file_path) if log2.file_path else 'N/A'

    result_html = f'''<div class="space-y-4">
        <div class="flex items-center justify-between">
            <h3 class="text-lg font-bold text-slate-800">Backup Diff</h3>
            <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 transition-colors p-1">
                <i class="fas fa-times text-lg"></i>
            </button>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-rose-50 border border-rose-200 rounded-lg px-3 py-1.5 text-rose-700 font-mono truncate">{html_lib.escape(fname1)}</div>
            <div class="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 text-emerald-700 font-mono truncate">{html_lib.escape(fname2)}</div>
        </div>
        <div class="overflow-auto max-h-[60vh] rounded-xl border border-slate-700">
            <table class="w-full bg-slate-900">
                <thead><tr>
                    <th class="px-2 py-1.5 text-left text-xs text-slate-400 border-r border-slate-700 w-1/2">Lama</th>
                    <th class="px-2 py-1.5 text-left text-xs text-slate-400 w-1/2">Baru</th>
                </tr></thead>
                <tbody>{table_rows}</tbody>
            </table>
        </div>
    </div>
    <script>
        document.getElementById('modal-content').classList.remove('max-w-xl');
        document.getElementById('modal-content').classList.add('max-w-5xl');
    </script>'''
    return HTMLResponse(result_html)


# Bulk backup
@router.post("/run/bulk")
async def trigger_bulk_backup(
    background_tasks: BackgroundTasks,
    request: Request,
    device_ids: list[int] = Form(...),
    command_id_str: str = Form(None, alias="command_id"),
    session: Session = SessionDep
):
    command_id = int(command_id_str) if command_id_str and command_id_str.isdigit() else None
    log_ids = []
    for device_id in device_ids:
        device = session.get(Device, device_id)
        if not device:
            continue
        backup_log = BackupLog(
            device_id=device_id,
            status='running',
            timestamp=datetime.now(timezone.utc),
            log_output='Bulk backup queued...',
        )
        session.add(backup_log)
        session.commit()
        session.refresh(backup_log)
        background_tasks.add_task(run_backup, device_id, backup_log.id, command_id)
        log_ids.append(backup_log.id)

    msg = f'Bulk backup started for {len(log_ids)} device(s).'
    if request.headers.get('HX-Request'):
        response = HTMLResponse('')
        response.headers['HX-Trigger'] = f'{{"refreshList": "", "showToast": {{"message": "{msg}", "type": "info"}}}}'
        return response
    return RedirectResponse(url=f'/backups?msg={msg}', status_code=303)


@router.get("/{log_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_log(request: Request, log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return templates.TemplateResponse("log_delete_confirm.html", {"request": request, "log": log})


@router.post("/{log_id}/delete", response_class=HTMLResponse)
async def delete_log(request: Request, log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if log:
        if log.file_path and os.path.exists(log.file_path):
            try:
                os.remove(log.file_path)
            except OSError as e:
                logger.warning(f"Error removing backup config file: {e}")

        if log.session_log_path and os.path.exists(log.session_log_path):
            try:
                os.remove(log.session_log_path)
            except OSError as e:
                logger.warning(f"Error removing session log trace: {e}")

        session.delete(log)
        session.commit()

        if request.headers.get("HX-Request"):
            content = f'<tr hx-swap-oob="delete:#log-{log_id}"></tr>'
            response = HTMLResponse(content)
            response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Backup log entry deleted successfully!", "type": "success"}}'
            return response

    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Log entry not found", "type": "error"}}'
        return response

    return RedirectResponse(url="/backups", status_code=303)
