"""
Base class untuk network service (backup & push).
Berisi logika umum: build device params, manage log, run group.
"""
import os
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.logging_config import get_logger
from app.models import Device
from app.security import decrypt_password

logger = get_logger(__name__)


class BaseNetworkService:
    """
    Base class yang menyediakan helper umum untuk operasi jaringan.
    Subclass harus mengimplementasikan `_execute()`.
    """

    def _build_device_params(self, device: Device) -> dict:
        """Bangun parameter koneksi Netmiko dari device & credential."""
        credential = device.credential
        return {
            "device_type": device.device_type,
            "host": device.ip_address,
            "port": device.port,
            "username": credential.username,
            "password": decrypt_password(credential.password),
            "secret": decrypt_password(credential.secret) if credential.secret else None,
            "global_delay_factor": settings.netmiko_delay_factor,
        }

    def _ensure_backup_dir(self) -> None:
        """Pastikan direktori backup ada."""
        os.makedirs(settings.backup_dir, exist_ok=True)

    def _get_session_filepath(self, device: Device, prefix: str = "") -> str:
        """Generate path untuk session log file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix_part = f"_{prefix}" if prefix else ""
        filename = f"{device.hostname}{prefix_part}_{timestamp}_session.log"
        return os.path.join(settings.backup_dir, filename)

    def _save_log(
        self,
        session: Session,
        log_model_class,
        log_id: int | None,
        device_id: int,
        status: str,
        log_output: str,
        session_log_path: str | None = None,
        file_path: str | None = None,
        schedule_id: int | None = None,
    ) -> None:
        """Buat atau update log entry di database."""
        if log_id:
            log_entry = session.get(log_model_class, log_id)
            if log_entry:
                log_entry.status = status
                log_entry.log_output = log_output
                log_entry.session_log_path = session_log_path
                log_entry.schedule_id = schedule_id
                if file_path is not None:
                    log_entry.file_path = file_path
                session.add(log_entry)
                session.commit()
                return

        # Buat log baru jika log_id tidak ada atau tidak ditemukan
        kwargs = dict(
            device_id=device_id,
            status=status,
            timestamp=datetime.now(timezone.utc),
            log_output=log_output,
            session_log_path=session_log_path,
            schedule_id=schedule_id,
        )
        if file_path is not None:
            kwargs["file_path"] = file_path

        log_entry = log_model_class(**kwargs)
        session.add(log_entry)
        session.commit()

    def _run_group(
        self,
        group_id: int,
        run_fn: Callable,
        log_map: dict[int, int] | None = None,
        **kwargs,
    ) -> list[dict]:
        """Jalankan operasi ke semua device dalam group secara parallel."""
        with Session(engine) as session:
            devices = session.exec(
                select(Device).where(Device.group_id == group_id)
            ).all()

        results = []
        with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
            futures = [
                executor.submit(
                    run_fn,
                    device.id,
                    log_id=log_map.get(device.id) if log_map else None,
                    **kwargs,
                )
                for device in devices
            ]
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Thread error in group operation: {e}")
                    results.append({"status": "failed", "message": str(e)})

        return results
