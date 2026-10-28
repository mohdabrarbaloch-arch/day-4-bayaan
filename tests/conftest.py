"""Test fixtures: an isolated database and an authenticated client."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set these before app.config is imported. A real file (not :memory:) so WAL mode
# behaves the way it does in production.
_TMP_DB = Path(tempfile.mkdtemp(prefix="bayaan-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["SECRET_KEY"] = "test-secret-not-used-in-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["CLOUD_API_KEY"] = ""
os.environ["OLLAMA_BASE_URL"] = ""
# The limiter is in-process and shared by every test in the session, so the
# production budgets (10/min on auth) would trip partway through the suite.
# Rate limiting gets its own dedicated test instead.
os.environ["RATE_LIMIT_AUTH"] = "10000/minute"
os.environ["RATE_LIMIT_RUNS"] = "10000/minute"

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import reset_limits  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_limiter():
    """Every test starts with an empty rate-limit window."""
    reset_limits()
    yield
    reset_limits()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(f"sqlite:///{_TMP_DB}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override() -> Iterator[Session]:
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_counter = {"n": 0}


@pytest.fixture
def auth(client: TestClient) -> dict:
    """Register a fresh user and return the bearer header."""
    _counter["n"] += 1
    email = f"tester{_counter['n']}@mailcatch.dev"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": "Test User", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
