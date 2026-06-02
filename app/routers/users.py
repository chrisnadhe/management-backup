from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import hash_password, get_current_user, is_admin, auth_context
from app.database import SessionDep
from app.logging_config import get_logger
from app.models import User, UserRole
from app.templates import templates

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


def _require_admin_or_redirect(request: Request):
    """Return current user jika admin, else return RedirectResponse."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("", response_class=HTMLResponse)
async def list_users(request: Request, session: Session = SessionDep):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    users = session.exec(select(User).order_by(User.created_at)).all()
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        **auth_context(request),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_user_form(request: Request):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result
    return templates.TemplateResponse("user_form.html", {
        "request": request,
        "roles": [r.value for r in UserRole],
        **auth_context(request),
    })


@router.post("/new", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    new_password: str = Form(...),
    role: str = Form(...),
    session: Session = SessionDep,
):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    # Cek duplikat username
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        return templates.TemplateResponse("user_form.html", {
            "request": request,
            "error": f"Username '{username}' sudah digunakan.",
            "roles": [r.value for r in UserRole],
            **auth_context(request),
        }, status_code=400)

    if len(new_password) < 8:
        return templates.TemplateResponse("user_form.html", {
            "request": request,
            "error": "Password minimal 8 karakter.",
            "roles": [r.value for r in UserRole],
            **auth_context(request),
        }, status_code=400)

    user = User(
        username=username,
        hashed_password=hash_password(new_password),
        role=UserRole(role),
        is_active=True,
    )
    session.add(user)
    session.commit()
    logger.info(f"User '{username}' created with role={role}")

    if request.headers.get("HX-Request"):
        users = session.exec(select(User).order_by(User.created_at)).all()
        response = templates.TemplateResponse("users_table.html", {
            "request": request,
            "users": users,
            **auth_context(request),
        })
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "User {username} created!", "type": "success"}}}}'
        return response

    return RedirectResponse(url="/users", status_code=303)


@router.get("/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(request: Request, user_id: int, session: Session = SessionDep):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse("user_form.html", {
        "request": request,
        "user": user,
        "roles": [r.value for r in UserRole],
        **auth_context(request),
    })


@router.post("/{user_id}/edit", response_class=HTMLResponse)
async def update_user(
    request: Request,
    user_id: int,
    username: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(False),  # Fix: Default harus False jika checkbox tidak dicentang
    new_password: str = Form(None),
    session: Session = SessionDep,
):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    current = get_current_user(request)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Jangan biarkan admin menonaktifkan dirinya sendiri
    if current and current.id == user_id and not is_active:
        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = '{"showToast": {"message": "Tidak bisa menonaktifkan akun sendiri!", "type": "error"}}'
            return response
        return RedirectResponse(url="/users?error=Cannot deactivate own account", status_code=303)

    user.username = username
    user.role = UserRole(role)
    user.is_active = is_active
    if new_password and len(new_password) >= 8:
        user.hashed_password = hash_password(new_password)

    session.add(user)
    session.commit()
    logger.info(f"User '{username}' updated")

    if request.headers.get("HX-Request"):
        users = session.exec(select(User).order_by(User.created_at)).all()
        response = templates.TemplateResponse("users_table.html", {
            "request": request,
            "users": users,
            **auth_context(request),
        })
        response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "User {username} updated!", "type": "success"}}}}'
        return response

    return RedirectResponse(url="/users", status_code=303)


@router.get("/{user_id}/delete/confirm", response_class=HTMLResponse)
async def delete_user_confirm(request: Request, user_id: int, session: Session = SessionDep):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    user = session.get(User, user_id)
    if not user:
        return HTMLResponse('<p class="text-rose-500 text-center py-4">User not found</p>')

    html = f'''<div class="p-6 text-center space-y-6">
        <div class="w-16 h-16 bg-rose-100 rounded-full flex items-center justify-center mx-auto">
            <i class="fas fa-exclamation-triangle text-2xl text-rose-600"></i>
        </div>
        <div>
            <h3 class="text-xl font-bold text-slate-900 mb-2">Delete User</h3>
            <p class="text-sm text-slate-500">Are you sure you want to delete user <span class="font-bold text-slate-800">"{user.username}"</span>?</p>
            <p class="text-xs text-rose-500 mt-2 font-medium">This action cannot be undone.</p>
        </div>
        <div class="flex items-center justify-center gap-3 pt-4 border-t border-slate-100">
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-semibold transition-colors">Cancel</button>
            <button hx-post="/users/{user.id}/delete" hx-target="#users-table-container" hx-swap="outerHTML" class="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-sm font-semibold shadow-lg shadow-rose-600/20 transition-all flex items-center gap-2">
                <i class="fas fa-trash-alt"></i> Yes, Delete User
            </button>
        </div>
    </div>'''
    return HTMLResponse(html)


@router.post("/{user_id}/delete", response_class=HTMLResponse)
async def delete_user(request: Request, user_id: int, session: Session = SessionDep):
    result = _require_admin_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result

    current = get_current_user(request)
    user = session.get(User, user_id)

    if user:
        # Jangan hapus diri sendiri
        if current and current.id == user_id:
            if request.headers.get("HX-Request"):
                response = HTMLResponse("")
                response.headers["HX-Trigger"] = '{"closeModal": "", "showToast": {"message": "Tidak bisa menghapus akun sendiri!", "type": "error"}}'
                return response
            return RedirectResponse(url="/users?error=Cannot delete own account", status_code=303)

        username = user.username
        session.delete(user)
        session.commit()
        logger.info(f"User '{username}' deleted")

        if request.headers.get("HX-Request"):
            response = HTMLResponse("")
            response.headers["HX-Trigger"] = f'{{"closeModal": "", "showToast": {{"message": "User {username} deleted!", "type": "success"}}}}'
            return response

    return RedirectResponse(url="/users", status_code=303)
