from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import DeviceGroup, Command
from app.templates import templates

router = APIRouter(prefix="/groups", tags=["groups"])

# Helper to fetch groups context
def get_groups_context(session: Session, request: Request):
    groups = session.exec(select(DeviceGroup)).all()
    commands = session.exec(select(Command)).all()
    return {"request": request, "groups": groups, "commands": commands}

@router.get("", response_class=HTMLResponse)
async def list_groups(request: Request, session: Session = SessionDep):
    context = get_groups_context(session, request)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("groups_table.html", context)
    return templates.TemplateResponse("groups.html", context)

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
    
    if request.headers.get("HX-Request"):
        context = get_groups_context(session, request)
        response = templates.TemplateResponse("groups_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Group {name} created successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/groups", status_code=303)

@router.get("/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_form(request: Request, group_id: int, session: Session = SessionDep):
    group = session.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
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
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group.name = name
    group.description = description
    session.add(group)
    session.commit()
    
    if request.headers.get("HX-Request"):
        context = get_groups_context(session, request)
        response = templates.TemplateResponse("groups_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Group {name} updated successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/groups", status_code=303)

@router.get("/{group_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_group(request: Request, group_id: int, session: Session = SessionDep):
    group = session.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return templates.TemplateResponse("group_delete_confirm.html", {"request": request, "group": group})

@router.post("/{group_id}/delete", response_class=HTMLResponse)
async def delete_group(request: Request, group_id: int, session: Session = SessionDep):
    group = session.get(DeviceGroup, group_id)
    if group:
        name = group.name
        session.delete(group)
        session.commit()
        
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Group {name} deleted successfully!", "type": "success"}}}}'
            return response
            
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Group not found", "type": "error"}}'
        return response
        
    return RedirectResponse(url="/groups", status_code=303)
