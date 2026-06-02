"""
Service untuk membersihkan backup lama berdasarkan kebijakan retensi.
Strategi: simpan N terbaru ATAU dalam X hari, mana yang lebih banyak.
"""
import os
from datetime import datetime, timezone, timedelta

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.logging_config import get_logger
from app.models import BackupLog, Device

logger = get_logger(__name__)


def cleanup_old_backups() -> dict:
    """
    Hapus backup yang melebihi kebijakan retensi untuk setiap device.
    Return stats: {deleted_records, deleted_files, errors}
    """
    retention_days = settings.backup_retention_days
    retention_count = settings.backup_retention_count
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    deleted_records = 0
    deleted_files = 0
    errors = []

    logger.info(
        f"Running backup retention cleanup "
        f"(keep last {retention_count} OR within {retention_days} days)"
    )

    with Session(engine) as session:
        devices = session.exec(select(Device)).all()

        for device in devices:
            # Ambil semua backup yang punya file, urut terbaru dulu
            all_backups = session.exec(
                select(BackupLog)
                .where(BackupLog.device_id == device.id)
                .where(BackupLog.file_path != None)  # noqa: E711
                .order_by(BackupLog.timestamp.desc())
            ).all()

            to_delete = []
            for idx, log in enumerate(all_backups):
                # Tandai untuk hapus jika LEBIH TUA dari cutoff DAN melebihi count
                is_over_count = idx >= retention_count
                # Pastikan timezone-aware comparison
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)
                is_over_age = log_ts < cutoff_date

                if is_over_count and is_over_age:
                    to_delete.append(log)

            for log in to_delete:
                # Hapus file di disk
                if log.file_path and os.path.exists(log.file_path):
                    try:
                        os.remove(log.file_path)
                        deleted_files += 1
                    except OSError as e:
                        errors.append(str(e))
                        logger.warning(f"Could not delete file {log.file_path}: {e}")

                if log.session_log_path and os.path.exists(log.session_log_path):
                    try:
                        os.remove(log.session_log_path)
                    except OSError as e:
                        logger.warning(f"Could not delete session log {log.session_log_path}: {e}")

                session.delete(log)
                deleted_records += 1

        session.commit()

    logger.info(
        f"Retention cleanup done: {deleted_records} records removed, "
        f"{deleted_files} files deleted, {len(errors)} errors"
    )
    return {"deleted_records": deleted_records, "deleted_files": deleted_files, "errors": errors}
