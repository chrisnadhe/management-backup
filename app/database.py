from sqlmodel import create_engine, Session
from typing import Generator
from fastapi import Depends

sqlite_file_name = "network_backup.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Depends(get_session)
