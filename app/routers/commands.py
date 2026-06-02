from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Command
from app.templates import templates

router = APIRouter(prefix="/commands", tags=["commands"])

# Helper to fetch commands context
def get_commands_context(session: Session, request: Request):
    commands = session.exec(select(Command)).all()
    return {"request": request, "commands": commands}

@router.get("", response_class=HTMLResponse)
async def list_commands(request: Request, session: Session = SessionDep):
    context = get_commands_context(session, request)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("commands_table.html", context)
    return templates.TemplateResponse("commands.html", context)

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
    
    if request.headers.get("HX-Request"):
        context = get_commands_context(session, request)
        response = templates.TemplateResponse("commands_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Command template {name} created successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/commands", status_code=303)

@router.get("/{command_id}/edit", response_class=HTMLResponse)
async def edit_command_form(request: Request, command_id: int, session: Session = SessionDep):
    command = session.get(Command, command_id)
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
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
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    command.name = name
    command.command_text = command_text
    command.platform = platform
    session.add(command)
    session.commit()
    
    if request.headers.get("HX-Request"):
        context = get_commands_context(session, request)
        response = templates.TemplateResponse("commands_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Command template {name} updated successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/commands", status_code=303)

@router.get("/{command_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_command(request: Request, command_id: int, session: Session = SessionDep):
    command = session.get(Command, command_id)
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    return templates.TemplateResponse("command_delete_confirm.html", {"request": request, "command": command})

@router.post("/{command_id}/delete", response_class=HTMLResponse)
async def delete_command(request: Request, command_id: int, session: Session = SessionDep):
    command = session.get(Command, command_id)
    if command:
        name = command.name
        session.delete(command)
        session.commit()
        
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Command template {name} deleted successfully!", "type": "success"}}}}'
            return response
            
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Command not found", "type": "error"}}'
        return response
        
    return RedirectResponse(url="/commands", status_code=303)
