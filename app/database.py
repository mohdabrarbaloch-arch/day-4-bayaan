"""Database engine + session plumbing. SQLite by default, Postgres if you point it there."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for every model."""


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # check_same_thread=False is required because FastAPI hands requests to a
        # thread pool and SQLite otherwise refuses the connection.
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


def build_engine(url: str | None = None):
    """Create an engine for `url`, enabling WAL + foreign keys on SQLite."""
    url = url or settings.database_url
    engine = create_engine(url, future=True, **_engine_kwargs(url))

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind=None) -> None:
    """Create tables. Safe to call repeatedly."""
    from . import models  # noqa: F401  (import registers the mappers)

    Base.metadata.create_all(bind=bind or engine)
