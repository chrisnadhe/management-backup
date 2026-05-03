from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import DeviceGroup, Command

router = APIRouter(prefix="/groups", tags=["groups"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
async def list_groups(request: Request, session: Session = SessionDep):
    groups = session.exec(select(DeviceGroup)).all()
    commands = session.exec(select(Command)).all()
    return templates.TemplateResponse("groups.html", {"request": request, "groups": groups, "commands": commands})

@router.get("/new", response_class=HTMLResponse)
async def new_group_form(request: Request):
    return templates.TemplateResponse("group_form.html", {"request": request})

@router.post("/new", response_class=HTMLResponse)
async def create_group(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    session: Session = SessionDep
):
    group = DeviceGroup(name=name, description=description)
    session.add(group)
    session.commit()
    return RedirectResponse(url="/groups", status_code=303)

@router.get("/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_form(request: Request, group_id: int, session: Session = SessionDep):
    group = session.get(DeviceGroup, group_id)
    return templates.TemplateResponse("group_form.html", {"request": request, "group": group})

@router.post("/{group_id}/edit", response_class=HTMLResponse)
async def update_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    description: str = Form(None),
    session: Session = SessionDep
):
    group = session.get(DeviceGroup, group_id)
    group.name = name
    group.description = description
    session.add(group)
    session.commit()
    return RedirectResponse(url="/groups", status_code=303)

@router.post("/{group_id}/delete", response_class=HTMLResponse)
async def delete_group(group_id: int, session: Session = SessionDep):
    group = session.get(DeviceGroup, group_id)
    if group:
        session.delete(group)
        session.commit()
    return RedirectResponse(url="/groups", status_code=303)
