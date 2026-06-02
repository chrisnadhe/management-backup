import os
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Form, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select, col, func

from app.database import SessionDep
from app.logging_config import get_logger
from app.models import PushLog, PushSchedule, Device, DeviceGroup
from app.services.push_service import run_push, run_push_group
from app.services.scheduler_service import add_push_job_to_scheduler, remove_push_job_from_scheduler
from app.templates import templates

logger = get_logger(__name__)
router = APIRouter(prefix="/push", tags=["push"])


def validate_cron(cron_expression: str) -> bool:
    """Validasi format cron expression menggunakan APScheduler."""
    try:
        CronTrigger.from_crontab(cron_expression)
        return True
    except Exception:
        return False


@router.get("", response_class=HTMLResponse)
async def push_dashboard(
    request: Request,
    session: Session = SessionDep,
    view: str = "form"  # form, schedules, logs
):
    devices = session.exec(select(Device)).all()
    groups = session.exec(select(DeviceGroup)).all()

    context = {
        "request": request,
        "devices": devices,
        "groups": groups,
        "view": view
    }

    if view == "logs":
        logs = session.exec(select(PushLog).order_by(PushLog.timestamp.desc()).limit(50)).all()
        context["logs"] = logs
    elif view == "schedules":
        schedules = session.exec(select(PushSchedule)).all()
        context["schedules"] = schedules

    return templates.TemplateResponse("push.html", context)


@router.post("/preview", response_class=HTMLResponse)
async def push_preview(
    request: Request,
    target_type: str = Form(...),
    target_id: int = Form(...),
    commands_text: str = Form(...),
    command_id: int = Form(None),
    session: Session = SessionDep,
):
    """Tampilkan modal konfirmasi sebelum push dieksekusi."""
    import html as html_lib

    if not commands_text or not commands_text.strip():
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"showToast": {"message": "Commands tidak boleh kosong!", "type": "error"}}'
        return response

    # Dapatkan info target
    target_name = ""
    device_count = 0
    if target_type == "device":
        device = session.get(Device, target_id)
        if not device:
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = '{"showToast": {"message": "Device tidak ditemukan!", "type": "error"}}'
            return response
        target_name = f"{device.hostname} ({device.ip_address})"
        device_count = 1
    elif target_type == "group":
        group = session.get(DeviceGroup, target_id)
        if not group:
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = '{"showToast": {"message": "Group tidak ditemukan!", "type": "error"}}'
            return response
        target_name = f"Group: {group.name}"
        device_count = len(group.devices) if group.devices else 0

    # Render preview commands
    commands_escaped = html_lib.escape(commands_text.strip())
    cmd_lines_html = "".join(
        f'<div class="flex items-start gap-2"><span class="text-indigo-400 select-none">$</span><span class="text-slate-200">{html_lib.escape(line.strip())}</span></div>'
        for line in commands_text.splitlines()
        if line.strip()
    )

    modal_html = f"""
    <div class="space-y-5">
        <div class="flex items-center gap-3">
            <div class="p-2.5 rounded-xl bg-rose-100">
                <i class="fas fa-exclamation-triangle text-rose-600 text-lg"></i>
            </div>
            <div>
                <h3 class="text-lg font-bold text-slate-800">Konfirmasi Push Config</h3>
                <p class="text-sm text-slate-500">Tindakan ini akan langsung mengeksekusi perintah ke device production.</p>
            </div>
        </div>

        <div class="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
            <div class="flex items-center justify-between text-sm">
                <span class="text-slate-500">Target</span>
                <span class="font-semibold text-slate-800">{html_lib.escape(target_name)}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
                <span class="text-slate-500">Jumlah Device</span>
                <span class="font-bold text-rose-600">{device_count} device(s)</span>
            </div>
        </div>

        <div>
            <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Commands yang akan dieksekusi:</p>
            <div class="bg-slate-900 rounded-xl p-4 space-y-1 max-h-40 overflow-y-auto font-mono text-xs">
                {cmd_lines_html}
            </div>
        </div>

        <div class="bg-rose-50 border border-rose-200 rounded-xl p-3">
            <p class="text-xs text-rose-700 font-medium">
                <i class="fas fa-shield-alt mr-1.5"></i>
                Ketik <strong>CONFIRM</strong> di bawah untuk mengaktifkan tombol eksekusi.
            </p>
        </div>

        <div>
            <input type="text" id="confirm-input" placeholder="Ketik CONFIRM untuk lanjut..."
                class="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-rose-400 focus:border-transparent"
                oninput="document.getElementById('confirm-push-btn').disabled = this.value !== 'CONFIRM'">
        </div>

        <form hx-post="/push/run" hx-target="body" hx-swap="none">
            <input type="hidden" name="target_type" value="{html_lib.escape(target_type)}">
            <input type="hidden" name="target_id" value="{target_id}">
            <input type="hidden" name="commands_text" value="{html_lib.escape(commands_text)}">
            <div class="flex justify-end gap-3">
                <button type="button" onclick="closeModal()"
                    class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 transition-colors">
                    Batal
                </button>
                <button type="submit" id="confirm-push-btn" disabled
                    class="px-5 py-2 bg-rose-600 text-white rounded-xl text-sm font-bold hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                    hx-on:htmx:after-request="closeModal()">
                    <i class="fas fa-paper-plane mr-1.5"></i>Eksekusi Push
                </button>
            </div>
        </form>
    </div>
    """
    return HTMLResponse(modal_html)



@router.post("/run")
async def trigger_push(
    background_tasks: BackgroundTasks,
    request: Request,
    target_type: str = Form(...),  # "device" or "group"
    target_id: int = Form(...),
    commands_text: str = Form(...),
    session: Session = SessionDep
):
    if not commands_text or not commands_text.strip():
        return RedirectResponse(url="/push?error=Commands text cannot be empty", status_code=303)

    log_map = {}
    if target_type == "device":
        device = session.get(Device, target_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        push_log = PushLog(
            device_id=device.id,
            status="running",
            timestamp=datetime.now(timezone.utc),
            log_output="Push queued..."
        )
        session.add(push_log)
        session.commit()
        session.refresh(push_log)

        background_tasks.add_task(run_push, device.id, commands_text, push_log.id)
        msg = f"Config push started for {device.hostname}."
        logger.info(msg)

    elif target_type == "group":
        group = session.get(DeviceGroup, target_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        if group.devices:
            for device in group.devices:
                push_log = PushLog(
                    device_id=device.id,
                    status="running",
                    timestamp=datetime.now(timezone.utc),
                    log_output="Push queued (Group)..."
                )
                session.add(push_log)
                session.commit()
                session.refresh(push_log)
                log_map[device.id] = push_log.id

        background_tasks.add_task(run_push_group, group.id, commands_text, log_map)
        msg = f"Group config push started for {group.name}."
        logger.info(msg)
    else:
        raise HTTPException(status_code=400, detail="Invalid target type")

    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = f'{{"showToast": {{"message": "{msg}", "type": "info"}}}}'
        return response

    return RedirectResponse(url=f"/push?msg={msg}&view=logs", status_code=303)


@router.post("/schedule")
async def create_push_schedule(
    request: Request,
    name: str = Form(...),
    cron_expression: str = Form(...),
    target_type: str = Form(...),
    target_id: int = Form(...),
    commands_text: str = Form(...),
    session: Session = SessionDep
):
    if not validate_cron(cron_expression):
        error_msg = f"Invalid cron expression: '{cron_expression}'"
        logger.warning(f"Push schedule create failed: {error_msg}")
        return RedirectResponse(url=f"/push?error={error_msg}&view=schedules", status_code=303)

    schedule = PushSchedule(
        name=name,
        cron_expression=cron_expression,
        commands_text=commands_text,
        enabled=True
    )

    if target_type == "device":
        schedule.limit_to_device_id = target_id
    elif target_type == "group":
        schedule.limit_to_group_id = target_id

    session.add(schedule)
    session.commit()
    session.refresh(schedule)

    add_push_job_to_scheduler(schedule)
    logger.info(f"Push schedule created: {name}")

    msg = "Push schedule created successfully!"
    return RedirectResponse(url=f"/push?msg={msg}&view=schedules", status_code=303)


@router.post("/schedule/{schedule_id}/toggle", response_class=HTMLResponse)
async def toggle_schedule(
    request: Request,
    schedule_id: int,
    session: Session = SessionDep
):
    schedule = session.get(PushSchedule, schedule_id)
    if schedule:
        schedule.enabled = not schedule.enabled
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

        if schedule.enabled:
            add_push_job_to_scheduler(schedule)
        else:
            remove_push_job_from_scheduler(schedule.id)

        status_text = "enabled" if schedule.enabled else "disabled"
        logger.info(f"Push schedule {schedule.name} {status_text}")

        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"refreshList": "", "showToast": {{"message": "Schedule {status_text}", "type": "success"}}}}'
            return response

    return RedirectResponse(url="/push?view=schedules", status_code=303)


@router.post("/schedule/{schedule_id}/delete", response_class=HTMLResponse)
async def delete_push_schedule(
    request: Request,
    schedule_id: int,
    session: Session = SessionDep
):
    schedule = session.get(PushSchedule, schedule_id)
    if schedule:
        remove_push_job_from_scheduler(schedule.id)

        for log in schedule.push_logs:
            if log.session_log_path and os.path.exists(log.session_log_path):
                try:
                    os.remove(log.session_log_path)
                except OSError as e:
                    logger.warning(f"Could not remove session log {log.session_log_path}: {e}")
            session.delete(log)

        session.delete(schedule)
        session.commit()
        logger.info(f"Push schedule deleted: {schedule.name}")

        if request.headers.get("HX-Request"):
            response = HTMLResponse(f'<tr hx-swap-oob="delete:#schedule-{schedule_id}"></tr>')
            response.headers["HX-Trigger"] = '{"showToast": {"message": "Schedule deleted", "type": "success"}}'
            return response

    return RedirectResponse(url="/push?view=schedules", status_code=303)


@router.get("/status/{log_id}", response_class=HTMLResponse)
async def get_push_status(
    log_id: int,
    view: str = "badge",
    session: Session = SessionDep
):
    log = session.get(PushLog, log_id)
    if not log:
        return HTMLResponse('<span class="text-slate-400">Unknown</span>')

    if view == "badge":
        if log.status == "running":
            trigger_attr = f'hx-get="/push/status/{log_id}?view=badge" hx-trigger="every 2s" hx-swap="outerHTML"'
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

        html = f"""
        <span class="inline-flex items-center px-2.5 py-0.5 text-xs font-bold rounded-full border {status_class}" {trigger_attr}>
            {spinner}{log.status}
        </span>
        """
        return HTMLResponse(html)

    elif view == "log":
        log_output = log.log_output or "Running config push..."
        if log.status == "running":
            trigger_attr = f'hx-get="/push/status/{log_id}?view=log" hx-trigger="every 2s" hx-swap="outerHTML"'
        else:
            trigger_attr = ""

        html = f"""
        <pre id="log-output-content-{log_id}"
             class="text-xs font-mono whitespace-pre-wrap text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-800 max-h-60 overflow-y-auto"
             {trigger_attr}>{log_output}</pre>
        """
        return HTMLResponse(html)

    return HTMLResponse("")
