import os
import re
from datetime import datetime, timezone

from netmiko import ConnectHandler
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.logging_config import get_logger
from app.models import Device, Command, BackupLog
from app.services.base_service import BaseNetworkService

logger = get_logger(__name__)

_service = BaseNetworkService()


def run_backup(
    device_id: int,
    log_id: int | None = None,
    command_id: int | None = None,
    schedule_id: int | None = None,
) -> dict:
    with Session(engine) as session:
        device = session.get(Device, device_id)

        if not device:
            logger.warning(f"Device ID {device_id} not found")
            if log_id:
                _service._save_log(
                    session, BackupLog, log_id, device_id,
                    "failed", "Device not found"
                )
            return {"status": "error", "message": "Device not found"}

        if not device.credential:
            logger.warning(f"Device {device.hostname} has no credential assigned")
            return {"status": "error", "message": "No credential assigned to device"}

        # Ambil command(s) yang akan dijalankan
        if command_id:
            command = session.get(Command, command_id)
            if command and command.platform == device.device_type:
                commands = [command]
            else:
                commands = []
        else:
            commands = session.exec(
                select(Command).where(Command.platform == device.device_type)
            ).all()

        if not commands:
            msg = f"No commands found for platform {device.device_type}"
            logger.warning(f"Device {device.hostname}: {msg}")
            return {"status": "error", "message": msg}

        # Siapkan koneksi
        _service._ensure_backup_dir()
        session_filepath = _service._get_session_filepath(device)
        device_params = _service._build_device_params(device)
        device_params["session_log"] = session_filepath

        try:
            with ConnectHandler(**device_params) as net_connect:
                if device.credential.secret:
                    net_connect.enable()

                prompt = net_connect.find_prompt()
                prompt_regex = re.escape(prompt)

                full_output = ""
                for cmd in commands:
                    for line in cmd.command_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            output = net_connect.send_command(
                                line, read_timeout=120, expect_string=prompt_regex
                            )
                            full_output += f"{prompt} {line}\n{output}\n"
                        except Exception as cmd_e:
                            full_output += f"! Error executing {line}: {cmd_e}\n"
                            raise cmd_e

            # Simpan file backup
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{device.hostname}_{timestamp}.txt"
            filepath = os.path.join(settings.backup_dir, filename)
            with open(filepath, "w") as f:
                f.write(full_output)

            logger.info(f"Backup successful for {device.hostname} → {filepath}")
            _service._save_log(
                session, BackupLog, log_id, device.id,
                "success", "Backup completed successfully.",
                session_log_path=session_filepath,
                file_path=filepath,
                schedule_id=schedule_id,
            )
            return {"status": "success", "message": "Backup successful"}

        except Exception as e:
            logger.error(f"Backup failed for {device.hostname}: {e}")
            _service._save_log(
                session, BackupLog, log_id, device.id,
                "failed", str(e),
                session_log_path=session_filepath if os.path.exists(session_filepath) else None,
                file_path=None,
                schedule_id=schedule_id,
            )
            return {"status": "failed", "message": str(e)}


def run_backup_group(
    group_id: int,
    log_map: dict[int, int] | None = None,
    command_id: int | None = None,
    schedule_id: int | None = None,
) -> list[dict]:
    logger.info(f"Starting group backup for group_id={group_id}")
    return _service._run_group(
        group_id,
        run_backup,
        log_map=log_map,
        command_id=command_id,
        schedule_id=schedule_id,
    )
