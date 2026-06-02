import csv
import io
import ipaddress
import os

from fastapi import APIRouter, BackgroundTasks, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlmodel import Session, select, col, func

from app.database import SessionDep
from app.logging_config import get_logger
from app.models import Device, Credential, DeviceGroup, Command
from app.services.connectivity_service import test_device_connection
from app.templates import templates

logger = get_logger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])


def validate_ip(ip: str) -> bool:
    """Validasi format IP address (IPv4 atau IPv6)."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def get_devices_context(session: Session, request: Request, q: str = "", page: int = 1, limit: int = 20):
    offset = (page - 1) * limit
    statement = select(Device)
    if q:
        statement = statement.where(
            (col(Device.hostname).contains(q)) |
            (col(Device.ip_address).contains(q))
        )

    total_count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    statement = statement.offset(offset).limit(limit)
    devices = session.exec(statement).all()

    commands = session.exec(select(Command)).all()
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()

    total_pages = (total_count + limit - 1) // limit

    return {
        "request": request,
        "devices": devices,
        "commands": commands,
        "credentials": credentials,
        "groups": groups,
        "q": q,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count
    }


@router.get("", response_class=HTMLResponse)
async def list_devices(
    request: Request,
    session: Session = SessionDep,
    q: str = "",
    page: int = 1,
    limit: int = 20
):
    context = get_devices_context(session, request, q, page, limit)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("devices_table.html", context)
    return templates.TemplateResponse("devices.html", context)


@router.get("/template")
async def download_template():
    template_path = "app/static/device_import_template.csv"
    if os.path.exists(template_path):
        return FileResponse(template_path, filename="device_import_template.csv", media_type="text/csv")
    return {"error": "Template not found"}


@router.get("/import/modal", response_class=HTMLResponse)
async def import_modal(request: Request):
    return templates.TemplateResponse("device_import_modal.html", {"request": request})


@router.post("/import")
async def import_devices(
    request: Request,
    file: UploadFile = File(...),
    session: Session = SessionDep
):
    content = await file.read()
    decoded = content.decode("utf-8")

    # Deteksi delimiter CSV (comma vs semicolon — Excel terkadang pakai semicolon)
    first_line = decoded.splitlines()[0] if decoded else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","

    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)

    count = 0
    errors = []

    for row in reader:
        try:
            hostname = row.get("hostname")
            ip_address = row.get("ip_address")
            port = int(row.get("port", 22))
            device_type = row.get("device_type", "cisco_ios")
            cred_name = row.get("credential_name")
            group_name = row.get("group_name")

            if not hostname or not ip_address or not cred_name:
                errors.append(f"Missing required fields for {hostname or 'unknown'}")
                continue

            if not validate_ip(ip_address):
                errors.append(f"Invalid IP address '{ip_address}' for {hostname}")
                continue

            cred = session.exec(select(Credential).where(Credential.name == cred_name)).first()
            if not cred:
                errors.append(f"Credential '{cred_name}' not found for {hostname}")
                continue

            group_id = None
            if group_name:
                group = session.exec(select(DeviceGroup).where(DeviceGroup.name == group_name)).first()
                if group:
                    group_id = group.id
                else:
                    errors.append(f"Group '{group_name}' not found for {hostname}, creating without group")

            device = Device(
                hostname=hostname,
                ip_address=ip_address,
                port=port,
                device_type=device_type,
                credential_id=cred.id,
                group_id=group_id
            )
            session.add(device)
            count += 1
        except Exception as e:
            errors.append(f"Error processing {row.get('hostname')}: {str(e)}")

    session.commit()
    logger.info(f"Device import: {count} imported, {len(errors)} errors")

    msg = f"Imported {count} devices."
    error_msg = ""
    if errors:
        error_msg = f"Imported {count} devices, but some errors occurred: " + "; ".join(errors[:2]) + ("..." if len(errors) > 2 else "")

    if request.headers.get("HX-Request"):
        context = get_devices_context(session, request)
        response = templates.TemplateResponse("devices_table.html", context)
        if error_msg:
            toast_data = f'{{"closeModal": "", "showToast": {{"message": "{error_msg}", "type": "error"}}}}'
        else:
            toast_data = f'{{"closeModal": "", "showToast": {{"message": "{msg}", "type": "success"}}}}'
        response.headers["HX-Trigger"] = toast_data
        return response

    if error_msg:
        return RedirectResponse(url=f"/devices?error={error_msg}", status_code=303)
    return RedirectResponse(url=f"/devices?msg={msg}", status_code=303)


@router.get("/new", response_class=HTMLResponse)
async def new_device_form(request: Request, session: Session = SessionDep):
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("device_form.html", {
        "request": request,
        "credentials": credentials,
        "groups": groups
    })


@router.post("/new", response_class=HTMLResponse)
async def create_device(
    request: Request,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    port: int = Form(22),
    device_type: str = Form(...),
    credential_id: int = Form(...),
    group_id: int = Form(None),
    session: Session = SessionDep
):
    if not validate_ip(ip_address):
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"showToast": {{"message": "Invalid IP address: {ip_address}", "type": "error"}}}}'
            return response
        return RedirectResponse(url=f"/devices?error=Invalid IP address: {ip_address}", status_code=303)

    device = Device(
        hostname=hostname,
        ip_address=ip_address,
        port=port,
        device_type=device_type,
        credential_id=credential_id,
        group_id=group_id
    )
    session.add(device)
    session.commit()
    logger.info(f"Device created: {hostname} ({ip_address})")

    if request.headers.get("HX-Request"):
        context = get_devices_context(session, request)
        response = templates.TemplateResponse("devices_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Device {hostname} created successfully!", "type": "success"}}}}'
        return response

    return RedirectResponse(url="/devices", status_code=303)


@router.get("/{device_id}/edit", response_class=HTMLResponse)
async def edit_device_form(request: Request, device_id: int, session: Session = SessionDep):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("device_form.html", {
        "request": request,
        "device": device,
        "credentials": credentials,
        "groups": groups
    })


@router.post("/{device_id}/edit", response_class=HTMLResponse)
async def update_device(
    request: Request,
    device_id: int,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    port: int = Form(...),
    device_type: str = Form(...),
    credential_id: int = Form(...),
    group_id: int = Form(None),
    session: Session = SessionDep
):
    if not validate_ip(ip_address):
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"showToast": {{"message": "Invalid IP address: {ip_address}", "type": "error"}}}}'
            return response
        return RedirectResponse(url=f"/devices?error=Invalid IP address: {ip_address}", status_code=303)

    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.hostname = hostname
    device.ip_address = ip_address
    device.port = port
    device.device_type = device_type
    device.credential_id = credential_id
    device.group_id = group_id
    session.add(device)
    session.commit()
    logger.info(f"Device updated: {hostname} ({ip_address})")

    if request.headers.get("HX-Request"):
        context = get_devices_context(session, request)
        response = templates.TemplateResponse("devices_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Device {hostname} updated successfully!", "type": "success"}}}}'
        return response

    return RedirectResponse(url="/devices", status_code=303)


@router.post("/{device_id}/test", response_class=HTMLResponse)
async def test_connection(
    device_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    session: Session = SessionDep
):
    # Run synchronously for immediate response (with timeout)
    result = test_device_connection(device_id)
    status = result['status']
    message = result['message']

    if status == 'online':
        badge = f'<span class="inline-flex items-center px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200"><i class="fas fa-circle text-[6px] mr-1.5"></i>Online</span>'
        toast_type = 'success'
    elif status == 'auth_error':
        badge = f'<span class="inline-flex items-center px-2 py-0.5 text-xs font-bold rounded-full bg-amber-50 text-amber-700 border border-amber-200"><i class="fas fa-circle text-[6px] mr-1.5"></i>Auth Error</span>'
        toast_type = 'error'
    else:
        badge = f'<span class="inline-flex items-center px-2 py-0.5 text-xs font-bold rounded-full bg-rose-50 text-rose-700 border border-rose-200"><i class="fas fa-circle text-[6px] mr-1.5"></i>Offline</span>'
        toast_type = 'error'
        
    device = session.get(Device, device_id)
    if device:
        from datetime import datetime, timezone
        device.last_status = status
        device.last_status_time = datetime.now(timezone.utc)
        session.add(device)
        session.commit()

    if request.headers.get('HX-Request'):
        response = HTMLResponse(badge)
        import json
        response.headers['HX-Trigger'] = json.dumps({"showToast": {"message": message, "type": toast_type}})
        return response
    return RedirectResponse(url='/devices', status_code=303)


@router.get("/{device_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_device(request: Request, device_id: int, session: Session = SessionDep):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return templates.TemplateResponse("device_delete_confirm.html", {"request": request, "device": device})


@router.post("/{device_id}/delete", response_class=HTMLResponse)
async def delete_device(request: Request, device_id: int, session: Session = SessionDep):
    device = session.get(Device, device_id)
    if device:
        hostname = device.hostname
        session.delete(device)
        session.commit()
        logger.info(f"Device deleted: {hostname}")

        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Device {hostname} deleted successfully!", "type": "success"}}}}'
            return response

    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Device not found", "type": "error"}}'
        return response

    return RedirectResponse(url="/devices", status_code=303)
