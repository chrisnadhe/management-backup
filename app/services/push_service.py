import os
from datetime import datetime, timezone
from netmiko import ConnectHandler
from sqlmodel import Session, select
from app.models import Device, PushLog
from app.database import engine
from concurrent.futures import ThreadPoolExecutor

BACKUP_DIR = "backups"

def run_push(device_id: int, commands_text: str, log_id: int | None = None, schedule_id: int | None = None):
    with Session(engine) as session:
        device = session.get(Device, device_id)
        
        if not device:
            if log_id:
                log = session.get(PushLog, log_id)
                if log:
                    log.status = "failed"
                    log.log_output = "Device not found"
                    session.add(log)
                    session.commit()
            return {"status": "error", "message": "Device not found"}
        
        if not device.credential:
             return {"status": "error", "message": "No credential assigned to device"}

        credential = device.credential
        
        if not commands_text or not commands_text.strip():
             return {"status": "error", "message": "No commands provided to push"}

        device_params = {
            "device_type": device.device_type,
            "host": device.ip_address,
            "port": device.port,
            "username": credential.username,
            "password": credential.password,
            "secret": credential.secret,
            "global_delay_factor": 4,
        }

        # Session Log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_filename = f"{device.hostname}_push_{timestamp}_session.log"
        session_filepath = os.path.join(BACKUP_DIR, session_filename)
        
        device_params["session_log"] = session_filepath
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        log_output = ""
        status = "success"
        
        try:
            with ConnectHandler(**device_params) as net_connect:
                if credential.secret:
                    net_connect.enable()
                
                # Split commands text into a list
                commands_list = [line.strip() for line in commands_text.splitlines() if line.strip()]
                
                output = net_connect.send_config_set(commands_list)
                log_output = output
                
                # Create or Update Log
                if log_id:
                    push_log = session.get(PushLog, log_id)
                    if push_log:
                        push_log.status = "success"
                        push_log.log_output = log_output
                        push_log.session_log_path = session_filepath
                        push_log.schedule_id = schedule_id
                        session.add(push_log)
                        session.commit()
                    else:
                        push_log = PushLog(
                            device_id=device.id,
                            status="success",
                            timestamp=datetime.now(timezone.utc),
                            log_output=log_output,
                            session_log_path=session_filepath,
                            schedule_id=schedule_id
                        )
                        session.add(push_log)
                        session.commit()
                else:
                    push_log = PushLog(
                        device_id=device.id,
                        status="success",
                        timestamp=datetime.now(timezone.utc),
                        log_output=log_output,
                        session_log_path=session_filepath,
                        schedule_id=schedule_id
                    )
                    session.add(push_log)
                    session.commit()
                
                return {"status": "success", "message": "Configuration push successful", "output": log_output}

        except Exception as e:
            status = "failed"
            log_output = str(e)
            
            if log_id:
                push_log = session.get(PushLog, log_id)
                if push_log:
                    push_log.status = "failed"
                    push_log.log_output = log_output
                    push_log.session_log_path = session_filepath if os.path.exists(session_filepath) else None
                    push_log.schedule_id = schedule_id
                    session.add(push_log)
                    session.commit()
                else:
                    push_log = PushLog(
                        device_id=device.id,
                        status="failed",
                        timestamp=datetime.now(timezone.utc),
                        log_output=log_output,
                        session_log_path=session_filepath if os.path.exists(session_filepath) else None,
                        schedule_id=schedule_id
                    )
                    session.add(push_log)
                    session.commit()
            else:
                push_log = PushLog(
                    device_id=device.id,
                    status="failed",
                    timestamp=datetime.now(timezone.utc),
                    log_output=log_output,
                    session_log_path=session_filepath if os.path.exists(session_filepath) else None,
                    schedule_id=schedule_id
                )
                session.add(push_log)
                session.commit()
            
            return {"status": "failed", "message": str(e), "output": log_output}

def run_push_group(group_id: int, commands_text: str, log_map: dict[int, int] | None = None, schedule_id: int | None = None):
    with Session(engine) as session:
        devices = session.exec(select(Device).where(Device.group_id == group_id)).all()
    
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for device in devices:
            log_id = log_map.get(device.id) if log_map else None
            futures.append(
                executor.submit(run_push, device.id, commands_text, log_id, schedule_id)
            )
        
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"status": "failed", "message": str(e)})
    
    return results
