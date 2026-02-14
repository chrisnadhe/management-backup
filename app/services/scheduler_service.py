from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from app.database import engine
from app.models import Schedule, Device
from app.services.backup_service import run_backup

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.start()
    # Load existing schedules
    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()
        for schedule in schedules:
            if schedule.enabled:
                add_job_to_scheduler(schedule)

def add_job_to_scheduler(schedule: Schedule):
    try:
        scheduler.add_job(
            run_backup_for_schedule, 
            CronTrigger.from_crontab(schedule.cron_expression), 
            id=str(schedule.id),
            replace_existing=True,
            args=[schedule.id] # Pass the schedule ID to the job function
        )
    except Exception as e:
        print(f"Failed to add job {schedule.id}: {e}")

def remove_job_from_scheduler(schedule_id: int):
    try:
        scheduler.remove_job(str(schedule_id))
    except Exception:
        pass # Job might not exist

def run_backup_for_schedule(schedule_id: int):
    # This function is called by the scheduler
    with Session(engine) as session:
        devices = session.exec(select(Device)).all()
        for device in devices:
            print(f"Starting backup for {device.hostname}")
            run_backup(device.id)
