from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Credential encryption
    secret_key: str

    # Session auth
    session_secret_key: str = "change-me-in-production-32-chars!!"
    session_max_age: int = 86400  # 24 jam dalam detik

    # Database
    db_url: str = "sqlite:///network_backup.db"

    # Backup
    backup_dir: str = "backups"

    # Backup retention
    backup_retention_days: int = 30    # Hapus jika lebih tua dari X hari
    backup_retention_count: int = 10   # Atau simpan N terbaru per device

    # Netmiko
    netmiko_delay_factor: int = 4

    # Thread pool untuk group operations
    max_workers: int = 5


settings = Settings()
