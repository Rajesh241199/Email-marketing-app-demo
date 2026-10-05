"""Shared pytest fixtures.

Assumes ``alembic upgrade head`` has already been run against ``TEST_DATABASE_URL`` (see
docs/api/testing.md). Each test runs inside a SAVEPOINT that is rolled back afterwards, so
tests never see each other's data and the schema itself is never touched here.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.main import app

_engine = create_engine(settings.test_database_url, pool_pre_ping=True)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    connection = _engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, transaction: object) -> None:
        if transaction.nested and not transaction._parent.nested:  # type: ignore[attr-defined]
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
