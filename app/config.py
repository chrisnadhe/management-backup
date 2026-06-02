from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Security
    secret_key: str

    # Database
    db_url: str = "sqlite:///network_backup.db"

    # Backup
    backup_dir: str = "backups"

    # Netmiko
    netmiko_delay_factor: int = 4

    # Thread pool untuk group operations
    max_workers: int = 5


settings = Settings()
