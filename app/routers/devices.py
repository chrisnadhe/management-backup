from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Device, Credential, DeviceGroup

router = APIRouter(prefix="/devices", tags=["devices"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_devices(request: Request, session: Session = SessionDep):
    devices = session.exec(select(Device)).all()
    return templates.TemplateResponse("devices.html", {"request": request, "devices": devices})

@router.get("/new", response_class=HTMLResponse)
async def new_device_form(request: Request, session: Session = SessionDep):
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("device_form.html", {"request": request, "credentials": credentials, "groups": groups})

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
    return RedirectResponse(url="/devices", status_code=303)

@router.get("/{device_id}/edit", response_class=HTMLResponse)
async def edit_device_form(request: Request, device_id: int, session: Session = SessionDep):
    device = session.get(Device, device_id)
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("device_form.html", {"request": request, "device": device, "credentials": credentials, "groups": groups})

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
    device = session.get(Device, device_id)
    device.hostname = hostname
    device.ip_address = ip_address
    device.port = port
    device.device_type = device_type
    device.credential_id = credential_id
    device.group_id = group_id
    session.add(device)
    session.commit()
    return RedirectResponse(url="/devices", status_code=303)

@router.post("/{device_id}/delete", response_class=HTMLResponse)
async def delete_device(device_id: int, session: Session = SessionDep):
    device = session.get(Device, device_id)
    if device:
        session.delete(device)
        session.commit()
    return RedirectResponse(url="/devices", status_code=303)
