from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, settings
from app.deps import COOKIE_NAME, require_roles
from app.models import ROLE_FINANCE_HEAD, AuditLog, User
from app.security import TOKEN_MINUTES, create_access_token
from tests.conftest import CLERK_PW, FINANCE_PW


def login(client, username="clerk", password=CLERK_PW):
    return client.post("/api/auth/login", json={"username": username, "password": password})

def as_cookie(token):
    return {"Cookie": f"{COOKIE_NAME}={token}"}

def test_login_success_returns_user_without_secrets(client):
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "clerk"
    assert body["role"] == "issue_clerk"
    assert "password" not in response.text


def test_session_cookie_is_httponly_and_strict(client):
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert COOKIE_NAME in cookie


def test_wrong_password_is_rejected(client):
    response = login(client, password="not-the-password-1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password."


def test_unknown_user_gets_the_same_message(client):
    response = login(client, username="nobody", password="whatever-pass-1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password."


def test_me_requires_sign_in(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_signed_in_user(client):
    login(client, "finance", FINANCE_PW)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["role"] == "finance_head"


def test_logout_ends_the_session(client):
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_lockout_after_five_failures_even_with_correct_password(client):
    for _ in range(5):
        assert login(client, password="wrong-password-1").status_code == 401
    assert login(client).status_code == 429


def test_login_attempts_are_audited(client, engine):
    login(client, password="wrong-password-1")
    login(client)
    with Session(engine) as session:
        actions = set(session.scalars(select(AuditLog.action)))
    assert {"login.failed", "login.success"} <= actions


def test_inactive_user_cannot_sign_in(client, engine):
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.username == "clerk"))
        user.is_active = False
        session.commit()
    assert login(client).status_code == 401


def test_valid_token_in_cookie_header_is_accepted(client, engine):
    with Session(engine) as session:
        user_id = session.scalar(select(User.id).where(User.username == "clerk"))
    good = create_access_token(user_id, "issue_clerk", settings.jwt_secret)
    response = client.get("/api/auth/me", headers=as_cookie(good))
    assert response.status_code == 200
    assert response.json()["username"] == "clerk"


def test_token_signed_with_another_secret_is_rejected(client, engine):
    with Session(engine) as session:
        user_id = session.scalar(select(User.id).where(User.username == "clerk"))
    bad = create_access_token(user_id, "issue_clerk", "another-secret-that-is-long-enough-123456")
    assert client.get("/api/auth/me", headers=as_cookie(bad)).status_code == 401


def test_expired_token_is_rejected(client, engine):
    with Session(engine) as session:
        user_id = session.scalar(select(User.id).where(User.username == "clerk"))
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=TOKEN_MINUTES + 5)
    expired = create_access_token(user_id, "issue_clerk", settings.jwt_secret, now=long_ago)
    assert client.get("/api/auth/me", headers=as_cookie(expired)).status_code == 401


def test_extra_fields_in_login_are_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "clerk", "password": CLERK_PW, "role": "finance_head"},
    )
    assert response.status_code == 422


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture()
def role_client(engine):
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        with maker() as session:
            yield session

    mini = FastAPI()

    @mini.get("/finance-only")
    def finance_only(user: User = Depends(require_roles(ROLE_FINANCE_HEAD))):
        return {"ok": True}

    mini.dependency_overrides[get_session] = override

    def with_user(username=None):
        if username is None:
            return TestClient(mini)
        with maker() as session:
            user = session.scalar(select(User).where(User.username == username))
            token = create_access_token(user.id, user.role, settings.jwt_secret)
        return TestClient(mini, headers=as_cookie(token))

    return with_user


def test_clerk_is_forbidden_from_finance_routes(role_client):
    assert role_client("clerk").get("/finance-only").status_code == 403


def test_finance_head_can_use_finance_routes(role_client):
    assert role_client("finance").get("/finance-only").status_code == 200


def test_anonymous_gets_401_on_finance_routes(role_client):
    assert role_client().get("/finance-only").status_code == 401