"""
Database engine and session setup.

Uses SQLite for the 8-day demo scope (see config.py's database_url comment
for why). The `connect_args` check_same_thread=False is SQLite-specific —
it's needed because FastAPI can use the same connection across threads in
a way SQLite is cautious about by default; this is safe here because we're
not sharing a single connection across concurrent requests in any way that
would corrupt data at demo scale.

get_db() follows FastAPI's standard dependency-injection pattern: yield a
session, ensure it's closed after the request, even on error.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Creates all tables. Called explicitly (not on import) so that importing
    this module never has a side effect — tests and scripts control when
    the schema actually gets created.
    """
    # Import models here (not at module top) so Base.metadata knows about
    # them before create_all runs, without creating a circular import at
    # module-load time between database.py and db_models.py.
    from app.models import db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
