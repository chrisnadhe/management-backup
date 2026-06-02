from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select, col, func
from app.database import SessionDep
from app.models import BackupLog, Device
from app.templates import templates
import os

router = APIRouter(prefix="/logs", tags=["logs"])

# Helper to fetch logs context
def get_logs_context(session: Session, request: Request, q: str = "", page: int = 1, limit: int = 20):
    offset = (page - 1) * limit
    statement = select(BackupLog).join(Device, isouter=True)
    if q:
        statement = statement.where(
            (col(Device.hostname).contains(q)) | 
            (col(BackupLog.status).contains(q))
        )
    
    total_count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    statement = statement.order_by(BackupLog.timestamp.desc()).offset(offset).limit(limit)
    logs = session.exec(statement).all()
    
    total_pages = (total_count + limit - 1) // limit
    
    return {
        "request": request, 
        "logs": logs,
        "q": q,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count
    }

@router.get("", response_class=HTMLResponse)
async def list_logs(
    request: Request, 
    session: Session = SessionDep,
    q: str = "",
    page: int = 1,
    limit: int = 20
):
    context = get_logs_context(session, request, q, page, limit)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse("logs_table.html", context)
    return templates.TemplateResponse("logs.html", context)

@router.get("/view/{log_id}", response_class=HTMLResponse)
async def view_log(request: Request, log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    session_content = ""
    if log.session_log_path and os.path.exists(log.session_log_path):
        with open(log.session_log_path, "r", encoding="utf-8", errors="ignore") as f:
            session_content = f.read().strip()
            
    return templates.TemplateResponse("log_view.html", {
        "request": request, 
        "log": log, 
        "session_content": session_content
    })

@router.get("/content/{log_id}", response_class=HTMLResponse)
async def view_log_content(log_id: int, session: Session = SessionDep):
    log = session.get(BackupLog, log_id)
    if not log:
        return HTMLResponse('<pre class="bg-slate-950 text-rose-400 p-5 rounded-2xl">Log not found</pre>')
        
    session_content = ""
    if log.session_log_path and os.path.exists(log.session_log_path):
        with open(log.session_log_path, "r", encoding="utf-8", errors="ignore") as f:
            session_content = f.read().strip()
            
    if log.status == "running":
        trigger_attr = f'hx-get="/logs/content/{log_id}" hx-trigger="every 2s" hx-swap="outerHTML"'
    else:
        trigger_attr = ""
        
    html = f"""
    <pre id="session-log-content-{log_id}"
         class="bg-slate-950 text-emerald-400 p-5 rounded-2xl overflow-auto h-96 whitespace-pre-wrap border border-slate-800/80 font-mono text-xs shadow-inner leading-relaxed"
         {trigger_attr}>{session_content or 'Establishing Netmiko session trace output...'}</pre>
    """
    return HTMLResponse(html)
