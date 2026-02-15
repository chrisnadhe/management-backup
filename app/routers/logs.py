from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import SessionDep
from app.models import BackupLog
import os

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_logs(request: Request, session: Session = SessionDep):
    logs = session.exec(select(BackupLog).order_by(BackupLog.timestamp.desc())).all()
    # Eager load device
    return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})

@router.get("/view/{log_id}", response_class=HTMLResponse)
async def view_log(request: Request, log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    session_content = ""
    if log.session_log_path and os.path.exists(log.session_log_path):
        with open(log.session_log_path, "r") as f:
            session_content = f.read()
            
    return templates.TemplateResponse("log_view.html", {"request": request, "log": log, "session_content": session_content})
