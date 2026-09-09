"""Database engine and session factory (local SQLite)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.database.models import Base


def create_db_engine(settings: Settings):
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    is_sqlite = settings.database_url.startswith("sqlite")
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )


def init_db(settings: Settings) -> sessionmaker[Session]:
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
