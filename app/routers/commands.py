from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Command

router = APIRouter(prefix="/commands", tags=["commands"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
async def list_commands(request: Request, session: Session = SessionDep):
    commands = session.exec(select(Command)).all()
    return templates.TemplateResponse("commands.html", {"request": request, "commands": commands})

@router.get("/new", response_class=HTMLResponse)
async def new_command_form(request: Request):
    return templates.TemplateResponse("command_form.html", {"request": request})

@router.post("/new", response_class=HTMLResponse)
async def create_command(
    request: Request,
    name: str = Form(...),
    command_text: str = Form(...),
    platform: str = Form(...),
    session: Session = SessionDep
):
    command = Command(name=name, command_text=command_text, platform=platform)
    session.add(command)
    session.commit()
    return RedirectResponse(url="/commands", status_code=303)

@router.get("/{command_id}/edit", response_class=HTMLResponse)
async def edit_command_form(request: Request, command_id: int, session: Session = SessionDep):
    command = session.get(Command, command_id)
    return templates.TemplateResponse("command_form.html", {"request": request, "command": command})

@router.post("/{command_id}/edit", response_class=HTMLResponse)
async def update_command(
    request: Request,
    command_id: int,
    name: str = Form(...),
    command_text: str = Form(...),
    platform: str = Form(...),
    session: Session = SessionDep
):
    command = session.get(Command, command_id)
    command.name = name
    command.command_text = command_text
    command.platform = platform
    session.add(command)
    session.commit()
    return RedirectResponse(url="/commands", status_code=303)

@router.post("/{command_id}/delete", response_class=HTMLResponse)
async def delete_command(command_id: int, session: Session = SessionDep):
    command = session.get(Command, command_id)
    if command:
        session.delete(command)
        session.commit()
    return RedirectResponse(url="/commands", status_code=303)
