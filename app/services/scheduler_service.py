from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from app.database import engine
from app.models import Schedule, Device
from app.services.backup_service import run_backup, run_backup_group

scheduler = BackgroundScheduler()

from app.services.backup_service import run_backup, run_backup_group

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
    # Load existing schedules
    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()
        for schedule in schedules:
            if schedule.enabled:
                add_job_to_scheduler(schedule)

def add_job_to_scheduler(schedule: Schedule):
    # Always remove existing job first to ensure fresh state
    remove_job_from_scheduler(schedule.id)
    
    if not schedule.enabled:
        # If disabled, ensure next_run is nullified in DB
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
            id=str(schedule.id),
            replace_existing=True,
            args=[schedule.id] 
        )
        
        # Update next_run in DB
        with Session(engine) as session:
            db_schedule = session.get(Schedule, schedule.id)
            if db_schedule:
                db_schedule.next_run = job.next_run_time
                session.add(db_schedule)
                session.commit()
                
    except Exception as e:
        print(f"Failed to add job {schedule.id}: {e}")

def remove_job_from_scheduler(schedule_id: int):
    try:
        scheduler.remove_job(str(schedule_id))
    except Exception:
        pass 

from datetime import datetime

def run_backup_for_schedule(schedule_id: int):
    with Session(engine) as session:
        schedule = session.get(Schedule, schedule_id)
        if not schedule:
            return

        command_id = schedule.command_id
        
        # Update last_run
        schedule.last_run = datetime.now()
        
        # Update next_run from APScheduler job
        job = scheduler.get_job(str(schedule_id))
        if job:
            schedule.next_run = job.next_run_time
            
        session.add(schedule)
        session.commit()

        if schedule.limit_to_device_id:
             print(f"Starting scheduled backup for Device ID {schedule.limit_to_device_id}")
             run_backup(schedule.limit_to_device_id, log_id=None, command_id=command_id, schedule_id=schedule_id)
             
        elif schedule.limit_to_group_id:
             print(f"Starting scheduled backup for Group ID {schedule.limit_to_group_id}")
             run_backup_group(schedule.limit_to_group_id, log_map=None, command_id=command_id, schedule_id=schedule_id)
             
        else:
             print("Starting scheduled backup for ALL devices")
             devices = session.exec(select(Device)).all()
             for device in devices:
                 run_backup(device.id, log_id=None, command_id=command_id, schedule_id=schedule_id)
