from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Schedule, Device, DeviceGroup, Command
from app.services.scheduler_service import add_job_to_scheduler, remove_job_from_scheduler
from app.templates import templates

router = APIRouter(prefix="/schedules", tags=["schedules"])

# Helper to fetch schedules context
def get_schedules_context(session: Session, request: Request):
    schedules = session.exec(select(Schedule)).all()
    return {"request": request, "schedules": schedules}

@router.get("", response_class=HTMLResponse)
async def list_schedules(request: Request, session: Session = SessionDep):
    context = get_schedules_context(session, request)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("schedules_table.html", context)
    return templates.TemplateResponse("schedules.html", context)

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
    
    # scheduler_service handle enabling logic internally
    add_job_to_scheduler(schedule)
    
    if request.headers.get("HX-Request"):
        context = get_schedules_context(session, request)
        response = templates.TemplateResponse("schedules_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Schedule {name} created successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/schedules", status_code=303)

@router.get("/{schedule_id}/edit", response_class=HTMLResponse)
async def edit_schedule_form(request: Request, schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
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
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Schedule not found", "type": "error"}}'
            return response
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
    
    if request.headers.get("HX-Request"):
        context = get_schedules_context(session, request)
        response = templates.TemplateResponse("schedules_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Schedule {name} updated successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/schedules", status_code=303)

@router.get("/{schedule_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_schedule(request: Request, schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return templates.TemplateResponse("schedule_delete_confirm.html", {"request": request, "schedule": schedule})

@router.post("/{schedule_id}/delete", response_class=HTMLResponse)
async def delete_schedule(request: Request, schedule_id: int, session: Session = SessionDep):
    schedule = session.get(Schedule, schedule_id)
    if schedule:
        name = schedule.name
        remove_job_from_scheduler(schedule.id)
        session.delete(schedule)
        session.commit()
        
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Schedule {name} deleted successfully!", "type": "success"}}}}'
            return response
            
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Schedule not found", "type": "error"}}'
        return response
        
    return RedirectResponse(url="/schedules", status_code=303)
