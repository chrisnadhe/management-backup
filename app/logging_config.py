"""
Logging configuration untuk Network Backup Manager.
Gunakan get_logger(__name__) di setiap module.
"""
import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Setup root logger dengan format yang konsisten."""
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Hindari duplikasi handler jika setup dipanggil lebih dari sekali
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    # Kurangi noise dari library eksternal
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("sqlmodel").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Dapatkan logger dengan nama module."""
    return logging.getLogger(name)
