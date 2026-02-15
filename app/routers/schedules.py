from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Schedule, Device, DeviceGroup, Command
from app.services.scheduler_service import add_job_to_scheduler, remove_job_from_scheduler

router = APIRouter(prefix="/schedules", tags=["schedules"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_schedules(request: Request, session: Session = SessionDep):
    schedules = session.exec(select(Schedule)).all()
    return templates.TemplateResponse("schedules.html", {"request": request, "schedules": schedules})

@router.get("/new", response_class=HTMLResponse)
async def new_schedule_form(request: Request, session: Session = SessionDep):
    devices = session.exec(select(Device)).all()
    groups = session.exec(select(DeviceGroup)).all()
    commands = session.exec(select(Command)).all()
    return templates.TemplateResponse("schedule_form.html", {
        "request": request, 
        "devices": devices, 
        "groups": groups, 
        "commands": commands
    })

@router.post("/create", response_class=HTMLResponse)
async def create_schedule(
    request: Request,
    name: str = Form(...),
    cron_expression: str = Form(...),
    enabled: bool = Form(False),
    limit_to_device_id: int = Form(None),
    limit_to_group_id: int = Form(None),
    command_id: int = Form(None),
    session: Session = SessionDep
):
    schedule = Schedule(
        name=name, 
        cron_expression=cron_expression,
        enabled=enabled,
        limit_to_device_id=limit_to_device_id,
        limit_to_group_id=limit_to_group_id,
        command_id=command_id
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    
    # scheduler_service handle enabling logic internally now
    add_job_to_scheduler(schedule)
    
    return RedirectResponse(url="/schedules", status_code=303)

@router.get("/{schedule_id}/edit", response_class=HTMLResponse)
async def edit_schedule_form(request: Request, schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    devices = session.exec(select(Device)).all()
    groups = session.exec(select(DeviceGroup)).all()
    commands = session.exec(select(Command)).all()
    return templates.TemplateResponse("schedule_form.html", {
        "request": request, 
        "schedule": schedule, 
        "devices": devices, 
        "groups": groups,
        "commands": commands
    })

@router.post("/{schedule_id}/update", response_class=HTMLResponse)
async def update_schedule(
    request: Request,
    schedule_id: int,
    name: str = Form(...),
    cron_expression: str = Form(...),
    enabled: bool = Form(False),
    limit_to_device_id: int = Form(None),
    limit_to_group_id: int = Form(None),
    command_id: int = Form(None),
    session: Session = SessionDep
):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        return RedirectResponse(url="/schedules?error=Schedule not found", status_code=303)
        
    schedule.name = name
    schedule.cron_expression = cron_expression
    schedule.enabled = enabled
    schedule.limit_to_device_id = limit_to_device_id
    schedule.limit_to_group_id = limit_to_group_id
    schedule.command_id = command_id
    
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    
    # Update job status in scheduler
    add_job_to_scheduler(schedule)
        
    return RedirectResponse(url="/schedules", status_code=303)

@router.post("/{schedule_id}/delete", response_class=HTMLResponse)
async def delete_schedule(schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    if schedule:
        remove_job_from_scheduler(schedule.id)
        session.delete(schedule)
        session.commit()
    return RedirectResponse(url="/schedules", status_code=303)
