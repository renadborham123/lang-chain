"""SQLAlchemy database configuration for local and future cloud deployments."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DB = _ROOT / "memory" / "employment.sqlite"
DATABASE_URL = os.getenv("JOBFLOW_DATABASE_URL", f"sqlite:///{_DEFAULT_DB.as_posix()}")


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 60} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # pragma: no cover - backend specific
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def init_database() -> None:
    _DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)
    from . import models  # noqa: F401 - register metadata

    Base.metadata.create_all(engine)
