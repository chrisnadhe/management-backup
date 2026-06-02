from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Credential
from app.templates import templates

router = APIRouter(prefix="/credentials", tags=["credentials"])

# Helper to fetch credentials context
def get_credentials_context(session: Session, request: Request):
    credentials = session.exec(select(Credential)).all()
    return {"request": request, "credentials": credentials}

@router.get("", response_class=HTMLResponse)
async def list_credentials(request: Request, session: Session = SessionDep):
    context = get_credentials_context(session, request)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("credentials_table.html", context)
    return templates.TemplateResponse("credentials.html", context)

@router.get("/new", response_class=HTMLResponse)
async def new_credential_form(request: Request):
    return templates.TemplateResponse("credential_form.html", {"request": request})

@router.post("/new", response_class=HTMLResponse)
async def create_credential(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    secret: str = Form(None),
    session: Session = SessionDep
):
    credential = Credential(name=name, username=username, password=password, secret=secret)
    session.add(credential)
    session.commit()
    
    if request.headers.get("HX-Request"):
        context = get_credentials_context(session, request)
        response = templates.TemplateResponse("credentials_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Credential {name} created successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/credentials", status_code=303)

@router.get("/{credential_id}/edit", response_class=HTMLResponse)
async def edit_credential_form(request: Request, credential_id: int, session: Session = SessionDep):
    credential = session.get(Credential, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return templates.TemplateResponse("credential_form.html", {"request": request, "credential": credential})

@router.post("/{credential_id}/edit", response_class=HTMLResponse)
async def update_credential(
    request: Request,
    credential_id: int,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    secret: str = Form(None),
    session: Session = SessionDep
):
    credential = session.get(Credential, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    credential.name = name
    credential.username = username
    credential.password = password
    credential.secret = secret
    session.add(credential)
    session.commit()
    
    if request.headers.get("HX-Request"):
        context = get_credentials_context(session, request)
        response = templates.TemplateResponse("credentials_table.html", context)
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Credential {name} updated successfully!", "type": "success"}}}}'
        return response
        
    return RedirectResponse(url="/credentials", status_code=303)

@router.get("/{credential_id}/delete/confirm", response_class=HTMLResponse)
async def confirm_delete_credential(request: Request, credential_id: int, session: Session = SessionDep):
    credential = session.get(Credential, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return templates.TemplateResponse("credential_delete_confirm.html", {"request": request, "credential": credential})

@router.post("/{credential_id}/delete", response_class=HTMLResponse)
async def delete_credential(request: Request, credential_id: int, session: Session = SessionDep):
    credential = session.get(Credential, credential_id)
    if credential:
        name = credential.name
        session.delete(credential)
        session.commit()
        
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "Credential {name} deleted successfully!", "type": "success"}}}}'
            return response
            
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Credential not found", "type": "error"}}'
        return response
        
    return RedirectResponse(url="/credentials", status_code=303)
