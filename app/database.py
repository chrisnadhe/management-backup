from sqlmodel import create_engine, Session
from sqlalchemy import event
from typing import Generator
from fastapi import Depends
from app.config import settings

connect_args = {"check_same_thread": False}
engine = create_engine(settings.db_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_conn, _):
    """Aktifkan WAL mode untuk concurrent read/write yang lebih baik."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Depends(get_session)
