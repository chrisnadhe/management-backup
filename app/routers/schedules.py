from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Schedule, Device, DeviceGroup
from app.services.scheduler_service import add_job_to_scheduler, remove_job_from_scheduler

router = APIRouter(prefix="/schedules", tags=["schedules"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_schedules(request: Request, session: Session = SessionDep):
    schedules = session.exec(select(Schedule)).all()
    # next_run logic: APScheduler job stores next run time. 
    # But for simplicity, we rely on the cron expression which represents the schedule.
    # If we want next_run displayed, we'd need to query scheduler.get_job(id).next_run_time
    # yes do that list backup logs and link to session log view.
    return templates.TemplateResponse("schedules.html", {"request": request, "schedules": schedules})

@router.get("/new", response_class=HTMLResponse)
async def new_schedule_form(request: Request):
    return templates.TemplateResponse("schedule_form.html", {"request": request})

@router.post("/new", response_class=HTMLResponse)
async def create_schedule(
    request: Request,
    name: str = Form(...),
    cron_expression: str = Form(...),
    enabled: bool = Form(True),
    limit_to_device_id: int = Form(None),
    limit_to_group_id: int = Form(None),
    session: Session = SessionDep
):
    schedule = Schedule(
        name=name, 
        cron_expression=cron_expression,
        limit_to_device_id=limit_to_device_id,
        limit_to_group_id=limit_to_group_id
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    # Add job to scheduler
    add_job_to_scheduler(schedule)
    return RedirectResponse(url="/schedules", status_code=303)

@router.post("/create", response_class=HTMLResponse)
async def create_schedule_logic( # Avoiding /new name conflict if any
    request: Request,
    name: str = Form(...),
    cron_expression: str = Form(...),
    enabled: bool = Form(False), # If not in form data (unchecked), default False. If checked, 'on' -> True? No casting 'on' to bool is True.
    session: Session = SessionDep
):
    # FastAPI casts "on" to True? Yes.
    schedule = Schedule(name=name, cron_expression=cron_expression, enabled=enabled)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    
    if enabled:
        add_job_to_scheduler(schedule)
    
    return RedirectResponse(url="/schedules", status_code=303)

@router.get("/{schedule_id}/edit", response_class=HTMLResponse)
async def edit_schedule_form(request: Request, schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    devices = session.exec(select(Device)).all()
    groups = session.exec(select(DeviceGroup)).all()
    return templates.TemplateResponse("schedule_form.html", {"request": request, "schedule": schedule, "devices": devices, "groups": groups})

@router.post("/{schedule_id}/update", response_class=HTMLResponse)
async def update_schedule(
    request: Request,
    schedule_id: int,
    name: str = Form(...),
    cron_expression: str = Form(...),
    limit_to_device_id: int = Form(None),
    limit_to_group_id: int = Form(None),
    session: Session = SessionDep
):
    schedule = session.get(Schedule, schedule_id)
    schedule.name = name
    schedule.cron_expression = cron_expression
    schedule.limit_to_device_id = limit_to_device_id
    schedule.limit_to_group_id = limit_to_group_id
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    
    # Update job
    remove_job_from_scheduler(schedule.id)
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
