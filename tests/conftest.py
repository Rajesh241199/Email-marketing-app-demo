import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, get_db
from core.deps import get_current_active_user

TEST_DB_URL = "sqlite:///./test_email_marketing.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    import models  # noqa — must import BEFORE create_all so metadata is populated
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    import os
    if os.path.exists("./test_email_marketing.db"):
        os.remove("./test_email_marketing.db")


TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def override_auth():
    """Return a fake active user so auth-protected endpoints work in tests."""
    from types import SimpleNamespace
    from models.account import UserStatus
    return SimpleNamespace(id=1, email="testuser@test.com", status=UserStatus.ACTIVE, account_id=1)


@pytest.fixture(scope="session")
def client(setup_db):  # depends on setup_db so test tables exist before any request
    import models  # noqa
    from main import app
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
