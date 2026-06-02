from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.logging_config import get_logger
from app.models import Schedule, PushSchedule, Device
from app.services.backup_service import run_backup, run_backup_group
from app.services.push_service import run_push, run_push_group

logger = get_logger(__name__)
scheduler = BackgroundScheduler()

# Dedicated thread pool — backup/push berjalan non-blocking dari scheduler
_executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="netbackup")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")

    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()
        for schedule in schedules:
            if schedule.enabled:
                add_job_to_scheduler(schedule)

        push_schedules = session.exec(select(PushSchedule)).all()
        for push_schedule in push_schedules:
            if push_schedule.enabled:
                add_push_job_to_scheduler(push_schedule)

    # Job retensi harian jam 3 pagi
    scheduler.add_job(
        _run_retention_cleanup,
        CronTrigger.from_crontab("0 3 * * *"),
        id="backup_retention_cleanup",
        replace_existing=True,
    )

    logger.info(
        f"Loaded {len(schedules)} backup and {len(push_schedules)} push schedule(s)"
    )


def _run_retention_cleanup():
    """Wrapper untuk retention cleanup agar bisa dipanggil dari scheduler."""
    from app.services.retention_service import cleanup_old_backups
    cleanup_old_backups()


def add_job_to_scheduler(schedule: Schedule):
    remove_job_from_scheduler(schedule.id)

    if not schedule.enabled:
        with Session(engine) as session:
            db_schedule = session.get(Schedule, schedule.id)
            if db_schedule:
                db_schedule.next_run = None
                session.add(db_schedule)
                session.commit()
        return

    try:
        job = scheduler.add_job(
            run_backup_for_schedule,
            CronTrigger.from_crontab(schedule.cron_expression),
            id=f"backup_{schedule.id}",
            replace_existing=True,
            args=[schedule.id],
        )
        with Session(engine) as session:
            db_schedule = session.get(Schedule, schedule.id)
            if db_schedule:
                db_schedule.next_run = job.next_run_time
                session.add(db_schedule)
                session.commit()
        logger.info(f"Backup job added: schedule_id={schedule.id}, next_run={job.next_run_time}")
    except Exception as e:
        logger.error(f"Failed to add backup job for schedule_id={schedule.id}: {e}")


def remove_job_from_scheduler(schedule_id: int):
    try:
        scheduler.remove_job(f"backup_{schedule_id}")
        logger.debug(f"Removed backup job: schedule_id={schedule_id}")
    except Exception:
        pass


def add_push_job_to_scheduler(schedule: PushSchedule):
    remove_push_job_from_scheduler(schedule.id)

    if not schedule.enabled:
        with Session(engine) as session:
            db_schedule = session.get(PushSchedule, schedule.id)
            if db_schedule:
                db_schedule.next_run = None
                session.add(db_schedule)
                session.commit()
        return

    try:
        job = scheduler.add_job(
            run_push_for_schedule,
            CronTrigger.from_crontab(schedule.cron_expression),
            id=f"push_{schedule.id}",
            replace_existing=True,
            args=[schedule.id],
        )
        with Session(engine) as session:
            db_schedule = session.get(PushSchedule, schedule.id)
            if db_schedule:
                db_schedule.next_run = job.next_run_time
                session.add(db_schedule)
                session.commit()
        logger.info(f"Push job added: schedule_id={schedule.id}, next_run={job.next_run_time}")
    except Exception as e:
        logger.error(f"Failed to add push job for schedule_id={schedule.id}: {e}")


def remove_push_job_from_scheduler(schedule_id: int):
    try:
        scheduler.remove_job(f"push_{schedule_id}")
        logger.debug(f"Removed push job: schedule_id={schedule_id}")
    except Exception:
        pass


def run_backup_for_schedule(schedule_id: int):
    """Dipanggil APScheduler — update metadata lalu submit ke thread pool (non-blocking)."""
    with Session(engine) as session:
        schedule = session.get(Schedule, schedule_id)
        if not schedule:
            logger.warning(f"Schedule ID {schedule_id} not found")
            return

        command_id = schedule.command_id
        schedule.last_run = datetime.now(timezone.utc)
        job = scheduler.get_job(f"backup_{schedule_id}")
        if job:
            schedule.next_run = job.next_run_time
        session.add(schedule)
        session.commit()

    # Jalankan backup di thread pool agar tidak memblock scheduler
    if schedule.limit_to_device_id:
        logger.info(f"Scheduled backup → Device ID {schedule.limit_to_device_id}")
        _executor.submit(run_backup, schedule.limit_to_device_id,
                         None, command_id, schedule_id)
    elif schedule.limit_to_group_id:
        logger.info(f"Scheduled backup → Group ID {schedule.limit_to_group_id}")
        _executor.submit(run_backup_group, schedule.limit_to_group_id,
                         None, command_id, schedule_id)
    else:
        logger.info("Scheduled backup → ALL devices")
        with Session(engine) as session:
            devices = session.exec(select(Device)).all()
        for device in devices:
            _executor.submit(run_backup, device.id, None, command_id, schedule_id)


def run_push_for_schedule(schedule_id: int):
    """Dipanggil APScheduler — update metadata lalu submit ke thread pool (non-blocking)."""
    with Session(engine) as session:
        schedule = session.get(PushSchedule, schedule_id)
        if not schedule:
            logger.warning(f"PushSchedule ID {schedule_id} not found")
            return

        commands_text = schedule.commands_text
        schedule.last_run = datetime.now(timezone.utc)
        job = scheduler.get_job(f"push_{schedule_id}")
        if job:
            schedule.next_run = job.next_run_time
        session.add(schedule)
        session.commit()

    if schedule.limit_to_device_id:
        logger.info(f"Scheduled push → Device ID {schedule.limit_to_device_id}")
        _executor.submit(run_push, schedule.limit_to_device_id,
                         commands_text, None, schedule_id)
    elif schedule.limit_to_group_id:
        logger.info(f"Scheduled push → Group ID {schedule.limit_to_group_id}")
        _executor.submit(run_push_group, schedule.limit_to_group_id,
                         commands_text, None, schedule_id)
    else:
        logger.info("Scheduled push → ALL devices")
        with Session(engine) as session:
            devices = session.exec(select(Device)).all()
        for device in devices:
            _executor.submit(run_push, device.id, commands_text, None, schedule_id)
