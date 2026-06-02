from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import (
    hash_password, verify_password,
    create_session, clear_session,
    get_current_user, has_no_users,
)
from app.database import SessionDep
from app.logging_config import get_logger
from app.models import User, UserRole
from app.templates import templates

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Jika sudah login, redirect ke dashboard
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    # Jika belum ada user sama sekali, redirect ke setup
    if has_no_users():
        return RedirectResponse(url="/setup", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = SessionDep,
):
    user = session.exec(select(User).where(User.username == username)).first()

    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        logger.warning(f"Failed login attempt for username: {username}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Username atau password salah."},
            status_code=401,
        )

    # Update last_login
    user.last_login = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    logger.info(f"User '{username}' logged in (role={user.role})")
    response = RedirectResponse(url="/", status_code=302)
    create_session(response, user.id)
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=302)
    clear_session(response)
    logger.info("User logged out")
    return response


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    # Jika sudah ada user, redirect ke login
    if not has_no_users():
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("setup.html", {"request": request})


@router.post("/setup", response_class=HTMLResponse)
async def setup_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = SessionDep,
):
    # Cek apakah sudah ada user
    if not has_no_users():
        return RedirectResponse(url="/login", status_code=302)

    if password != confirm_password:
        return templates.TemplateResponse(
            "setup.html",
            {"request": request, "error": "Password tidak cocok."},
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            "setup.html",
            {"request": request, "error": "Password minimal 8 karakter."},
            status_code=400,
        )

    admin = User(
        username=username,
        hashed_password=hash_password(password),
        role=UserRole.admin,
        is_active=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)

    logger.info(f"Admin user '{username}' created via setup")
    response = RedirectResponse(url="/", status_code=302)
    create_session(response, admin.id)
    return response
