import enum
from typing import Optional, List
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Relationship

class Credential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    username: str
    password: str
    secret: Optional[str] = None
    
    devices: List["Device"] = Relationship(back_populates="credential")

class DeviceGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = None
    
    devices: List["Device"] = Relationship(back_populates="group")

class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hostname: str = Field(index=True)
    ip_address: str
    port: int = Field(default=22)
    device_type: str = Field(default="cisco_ios") # netmiko device_type
    credential_id: Optional[int] = Field(default=None, foreign_key="credential.id")
    group_id: Optional[int] = Field(default=None, foreign_key="devicegroup.id")
    last_status: Optional[str] = None
    last_status_time: Optional[datetime] = None
    
    credential: Optional[Credential] = Relationship(back_populates="devices")
    group: Optional[DeviceGroup] = Relationship(back_populates="devices")
    backups: List["BackupLog"] = Relationship(back_populates="device")
    schedules: List["Schedule"] = Relationship(back_populates="device")
    push_logs: List["PushLog"] = Relationship(back_populates="device")
    push_schedules: List["PushSchedule"] = Relationship(back_populates="device")

class Command(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    command_text: str
    platform: str = Field(default="cisco_ios")

class BackupLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    schedule_id: Optional[int] = Field(default=None, foreign_key="schedule.id")
    status: str # "success", "failed"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    log_output: Optional[str] = None
    file_path: Optional[str] = None
    session_log_path: Optional[str] = None
    
    device: Optional[Device] = Relationship(back_populates="backups")
    schedule: Optional["Schedule"] = Relationship(back_populates="backups")

class Schedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cron_expression: str # e.g., "0 2 * * *"
    enabled: bool = Field(default=True)
    limit_to_device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    limit_to_group_id: Optional[int] = Field(default=None, foreign_key="devicegroup.id")
    command_id: Optional[int] = Field(default=None, foreign_key="command.id")
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    
    backups: List[BackupLog] = Relationship(back_populates="schedule")
    device: Optional[Device] = Relationship(back_populates="schedules") # Helpful for targeting lookup
    group: Optional[DeviceGroup] = Relationship() # Helpful for targeting lookup

class PushLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    schedule_id: Optional[int] = Field(default=None, foreign_key="pushschedule.id")
    status: str # "success", "failed"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    log_output: Optional[str] = None
    session_log_path: Optional[str] = None
    
    device: Optional[Device] = Relationship(back_populates="push_logs")
    schedule: Optional["PushSchedule"] = Relationship(back_populates="push_logs")

class PushSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cron_expression: str # e.g., "0 2 * * *"
    enabled: bool = Field(default=True)
    limit_to_device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    limit_to_group_id: Optional[int] = Field(default=None, foreign_key="devicegroup.id")
    commands_text: str
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    
    push_logs: List[PushLog] = Relationship(back_populates="schedule")
    device: Optional[Device] = Relationship(back_populates="push_schedules")
    group: Optional[DeviceGroup] = Relationship()


# ── Auth Models ────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: UserRole = Field(default=UserRole.user)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None


class AppSetting(SQLModel, table=True):
    """Key-value store untuk konfigurasi aplikasi yang bisa diubah via UI."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str
    description: Optional[str] = None
