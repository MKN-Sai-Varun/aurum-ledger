import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.routers.auth import limiter
from app.seed import seed_database

CLERK_PW = "clerk-demo-pass-1"
FINANCE_PW = "finance-demo-pass-1"
KARIGAR_PW = "karigar-demo-pass-1"

@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, CLERK_PW, FINANCE_PW, KARIGAR_PW)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine):
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override
    limiter.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.clear()