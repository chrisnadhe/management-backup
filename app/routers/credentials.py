from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import Credential

router = APIRouter(prefix="/credentials", tags=["credentials"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
async def list_credentials(request: Request, session: Session = SessionDep):
    credentials = session.exec(select(Credential)).all()
    return templates.TemplateResponse("credentials.html", {"request": request, "credentials": credentials})

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
    session.refresh(credential)
    return RedirectResponse(url="/credentials", status_code=303)

@router.get("/{credential_id}/edit", response_class=HTMLResponse)
async def edit_credential_form(request: Request, credential_id: int, session: Session = SessionDep):
    credential = session.get(Credential, credential_id)
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
    credential.name = name
    credential.username = username
    credential.password = password
    credential.secret = secret
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return RedirectResponse(url="/credentials", status_code=303)

@router.post("/{credential_id}/delete", response_class=HTMLResponse)
async def delete_credential(credential_id: int, session: Session = SessionDep):
    credential = session.get(Credential, credential_id)
    if credential:
        session.delete(credential)
        session.commit()
    return RedirectResponse(url="/credentials", status_code=303)
