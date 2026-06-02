from fastapi import APIRouter, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import auth_context, get_current_user, is_admin
from app.config import settings
from app.database import SessionDep
from app.logging_config import get_logger
from app.services.retention_service import cleanup_old_backups
from app.templates import templates

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = get_current_user(request)
    if not user or not is_admin(user):
        return RedirectResponse(url="/", status_code=302)

    current_settings = {
        "backup_retention_days": settings.backup_retention_days,
        "backup_retention_count": settings.backup_retention_count,
        "max_workers": settings.max_workers,
        "netmiko_delay_factor": settings.netmiko_delay_factor,
        "session_max_age": settings.session_max_age,
        "backup_dir": settings.backup_dir,
    }

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "current_settings": current_settings,
        **auth_context(request),
    })


@router.post("/retention/cleanup", response_class=HTMLResponse)
async def manual_cleanup(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Trigger manual retention cleanup."""
    user = get_current_user(request)
    if not user or not is_admin(user):
        return RedirectResponse(url="/", status_code=302)

    background_tasks.add_task(cleanup_old_backups)
    msg = "Backup retention cleanup started in background."
    logger.info(msg)

    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = f'{{"showToast": {{"message": "{msg}", "type": "info"}}}}'
        return response

    return RedirectResponse(url="/settings?msg=Cleanup started", status_code=303)
