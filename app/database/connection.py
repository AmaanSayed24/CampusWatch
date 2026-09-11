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
    _migrate(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _migrate(engine) -> None:
    """Lightweight column migrations for databases created by older versions.

    create_all() only adds missing *tables*, not columns, so new columns on
    existing tables are added here. Duplicate-column errors mean the migration
    already ran and are ignored.
    """
    from sqlalchemy import text

    statements = (
        "ALTER TABLE assignments ADD COLUMN manual_deadline BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE pdf_deadline_cache ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 0",
    )
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception:
                pass  # column already exists
