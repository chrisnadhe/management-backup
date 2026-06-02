from netmiko import ConnectHandler
from sqlmodel import Session

from app.database import engine
from app.logging_config import get_logger
from app.models import Device, PushLog
from app.services.base_service import BaseNetworkService

logger = get_logger(__name__)

_service = BaseNetworkService()


def run_push(
    device_id: int,
    commands_text: str,
    log_id: int | None = None,
    schedule_id: int | None = None,
) -> dict:
    with Session(engine) as session:
        device = session.get(Device, device_id)

        if not device:
            logger.warning(f"Device ID {device_id} not found")
            if log_id:
                _service._save_log(
                    session, PushLog, log_id, device_id,
                    "failed", "Device not found"
                )
            return {"status": "error", "message": "Device not found"}

        if not device.credential:
            logger.warning(f"Device {device.hostname} has no credential assigned")
            return {"status": "error", "message": "No credential assigned to device"}

        if not commands_text or not commands_text.strip():
            return {"status": "error", "message": "No commands provided to push"}

        # Siapkan koneksi
        _service._ensure_backup_dir()
        session_filepath = _service._get_session_filepath(device, prefix="push")
        device_params = _service._build_device_params(device)
        device_params["session_log"] = session_filepath

        try:
            with ConnectHandler(**device_params) as net_connect:
                if device.credential.secret:
                    net_connect.enable()

                commands_list = [
                    line.strip()
                    for line in commands_text.splitlines()
                    if line.strip()
                ]
                log_output = net_connect.send_config_set(commands_list)

            logger.info(f"Config push successful for {device.hostname}")
            _service._save_log(
                session, PushLog, log_id, device.id,
                "success", log_output,
                session_log_path=session_filepath,
                schedule_id=schedule_id,
            )
            return {
                "status": "success",
                "message": "Configuration push successful",
                "output": log_output,
            }

        except Exception as e:
            logger.error(f"Config push failed for {device.hostname}: {e}")
            import os
            _service._save_log(
                session, PushLog, log_id, device.id,
                "failed", str(e),
                session_log_path=session_filepath if os.path.exists(session_filepath) else None,
                schedule_id=schedule_id,
            )
            return {"status": "failed", "message": str(e), "output": str(e)}


def run_push_group(
    group_id: int,
    commands_text: str,
    log_map: dict[int, int] | None = None,
    schedule_id: int | None = None,
) -> list[dict]:
    logger.info(f"Starting group push for group_id={group_id}")
    return _service._run_group(
        group_id,
        run_push,
        log_map=log_map,
        commands_text=commands_text,
        schedule_id=schedule_id,
    )
