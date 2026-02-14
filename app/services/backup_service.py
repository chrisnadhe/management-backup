import os
from datetime import datetime
from netmiko import ConnectHandler
from sqlmodel import Session, select
from app.models import Device, Command, BackupLog
from app.database import engine

BACKUP_DIR = "backups"

def run_backup(device_id: int, log_id: int | None = None, command_id: int | None = None):
    with Session(engine) as session:
        device = session.get(Device, device_id)
        # If we have a log_id, fetch it to update later. 
        # But we need to keep session open or re-fetch.
        # Let's re-fetch at the end or just use ID.
        
        if not device:
            if log_id:
                # Update log if possible
                log = session.get(BackupLog, log_id)
                if log:
                    log.status = "failed"
                    log.log_output = "Device not found"
                    session.add(log)
                    session.commit()
            return {"status": "error", "message": "Device not found"}
        
        if not device.credential:
             return {"status": "error", "message": "No credential assigned to device"}

        credential = device.credential
        
        # Get commands for this platform
        if command_id:
            command = session.get(Command, command_id)
            if command and command.platform == device.device_type:
                commands = [command]
            else:
                commands = [] # Command mismatch or not found
        else:
            commands = session.exec(select(Command).where(Command.platform == device.device_type)).all()

        if not commands:
             return {"status": "error", "message": f"No commands found for platform {device.device_type} (or specific command mismatch)"}

        device_params = {
            "device_type": device.device_type,
            "host": device.ip_address,
            "port": device.port,
            "username": credential.username,
            "password": credential.password,
            "secret": credential.secret,
            "global_delay_factor": 4, # Increased for slower devices like MikroTik
        }

        # Session Log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_filename = f"{device.hostname}_{timestamp}_session.log"
        session_filepath = os.path.join(BACKUP_DIR, session_filename)
        
        # Update device_params to include session_log
        device_params["session_log"] = session_filepath
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        log_output = ""
        status = "success"
        
        try:
            with ConnectHandler(**device_params) as net_connect:
                if credential.secret:
                    net_connect.enable()
                
                # Dynamically find the prompt to use as expectation
                prompt = net_connect.find_prompt()
                import re
                prompt_regex = re.escape(prompt)
                
                full_output = ""
                for cmd in commands:
                    # Check if command has multiple lines
                    cmd_lines = cmd.command_text.splitlines()
                    for line in cmd_lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                             # Use the detected prompt regex to ensure we catch it
                             # Increase read_timeout significantly for long exports
                             output = net_connect.send_command(line, read_timeout=120, expect_string=prompt_regex)
                             full_output += f"{prompt} {line}\n"
                             full_output += output + "\n"
                        except Exception as cmd_e:
                             full_output += f"! Error executing {line}: {str(cmd_e)}\n"
                             raise cmd_e
                
                # Save to file
                filename = f"{device.hostname}_{timestamp}.txt"
                filepath = os.path.join(BACKUP_DIR, filename)
                
                with open(filepath, "w") as f:
                    f.write(full_output)
                
                log_output = "Backup completed successfully."
                
                # Create or Update Log
                if log_id:
                    backup_log = session.get(BackupLog, log_id)
                    if backup_log:
                        backup_log.status = "success"
                        backup_log.log_output = log_output
                        backup_log.file_path = filepath
                        backup_log.session_log_path = session_filepath
                        session.add(backup_log)
                        session.commit()
                    else:
                        # Log ID provided but not found? Should not happen. Create new.
                        backup_log = BackupLog(
                            device_id=device.id,
                            status="success",
                            timestamp=datetime.now(),
                            log_output=log_output,
                            file_path=filepath,
                            session_log_path=session_filepath
                        )
                        session.add(backup_log)
                        session.commit()
                else:
                    backup_log = BackupLog(
                        device_id=device.id,
                        status="success",
                        timestamp=datetime.now(),
                        log_output=log_output,
                        file_path=filepath,
                        session_log_path=session_filepath
                    )
                    session.add(backup_log)
                    session.commit()
                
                return {"status": "success", "message": "Backup successful"}

        except Exception as e:
            status = "failed"
            log_output = str(e)
            
            if log_id:
                backup_log = session.get(BackupLog, log_id)
                if backup_log:
                    backup_log.status = "failed"
                    backup_log.log_output = log_output
                    backup_log.session_log_path = session_filepath if os.path.exists(session_filepath) else None
                    session.add(backup_log)
                    session.commit()
                else:
                    backup_log = BackupLog(
                        device_id=device.id,
                        status="failed",
                        timestamp=datetime.now(),
                        log_output=log_output,
                        file_path=None,
                        session_log_path=session_filepath if os.path.exists(session_filepath) else None
                    )
                    session.add(backup_log)
                    session.commit()
            else:
                backup_log = BackupLog(
                    device_id=device.id,
                    status="failed",
                    timestamp=datetime.now(),
                    log_output=log_output,
                    file_path=None,
                    session_log_path=session_filepath if os.path.exists(session_filepath) else None
                )
                session.add(backup_log)
                session.commit()
            
            return {"status": "failed", "message": str(e)}

def run_backup_group(group_id: int, log_map: dict[int, int] | None = None, command_id: int | None = None):
    with Session(engine) as session:
        devices = session.exec(select(Device).where(Device.group_id == group_id)).all()
        results = []
        for device in devices:
            log_id = log_map.get(device.id) if log_map else None
            result = run_backup(device.id, log_id, command_id=command_id)
            results.append(result)
        return results
