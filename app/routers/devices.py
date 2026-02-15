from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Device, Credential, DeviceGroup, Command

router = APIRouter(prefix="/devices", tags=["devices"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_devices(request: Request, session: Session = SessionDep):
    devices = session.exec(select(Device)).all()
    commands = session.exec(select(Command)).all()
    credentials = session.exec(select(Credential)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("devices.html", {
        "request": request, 
        "devices": devices, 
        "commands": commands,
        "credentials": credentials,
        "groups": groups
    })

@router.get("/template")
async def download_template():
    import os
    template_path = "app/static/device_import_template.csv"
    if os.path.exists(template_path):
        return FileResponse(template_path, filename="device_import_template.csv", media_type="text/csv")
    return {"error": "Template not found"}

@router.post("/import")
async def import_devices(
    file: UploadFile = File(...),
    session: Session = SessionDep
):
    import csv
    import io

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    count = 0
    errors = []
    
    for row in reader:
        try:
            hostname = row.get('hostname')
            ip_address = row.get('ip_address')
            port = int(row.get('port', 22))
            device_type = row.get('device_type', 'cisco_ios')
            cred_name = row.get('credential_name')
            group_name = row.get('group_name')
            
            if not hostname or not ip_address or not cred_name:
                errors.append(f"Missing required fields for {hostname or 'unknown'}")
                continue
                
            # Lookup credential
            cred = session.exec(select(Credential).where(Credential.name == cred_name)).first()
            if not cred:
                errors.append(f"Credential '{cred_name}' not found for {hostname}")
                continue
                
            # Lookup group
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
    
    msg = f"Imported {count} devices."
    if errors:
        error_msg = f"Imported {count} devices, but some errors occurred: " + "; ".join(errors[:3]) + ("..." if len(errors) > 3 else "")
        return RedirectResponse(url=f"/devices?error={error_msg}", status_code=303)
        
    return RedirectResponse(url=f"/devices?msg={msg}", status_code=303)

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
