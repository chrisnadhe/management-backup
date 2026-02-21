from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, col, func
from app.database import SessionDep
from app.models import BackupLog, Device
import os

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_logs(
    request: Request, 
    session: Session = SessionDep,
    q: str = "",
    page: int = 1,
    limit: int = 20
):
    offset = (page - 1) * limit
    
    # Base query
    statement = select(BackupLog).join(Device, isouter=True)
    
    # Filtering
    if q:
        statement = statement.where(
            (col(Device.hostname).contains(q)) | 
            (col(BackupLog.status).contains(q))
        )
    
    # Total count for pagination
    total_count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    
    # Pagination and sorting
    statement = statement.order_by(BackupLog.timestamp.desc()).offset(offset).limit(limit)
    logs = session.exec(statement).all()
    
    total_pages = (total_count + limit - 1) // limit
    
    return templates.TemplateResponse("logs.html", {
        "request": request, 
        "logs": logs,
        "q": q,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count
    })

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
