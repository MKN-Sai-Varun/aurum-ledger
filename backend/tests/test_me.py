import re

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.main import app
from app.models import User
from tests.conftest import KARIGAR_PW
from tests.test_corrections import switch
from tests.test_issues import issue_body
from tests.test_karigars import sign_in


def sign_in_karigar(client):
    response = client.post(
        "/api/auth/login", json={"username": "murugesan", "password": KARIGAR_PW}
    )
    assert response.status_code == 200
    return response.json()


def test_a_karigar_login_has_the_karigar_role(client):
    user = sign_in_karigar(client)
    assert user["role"] == "karigar"
    assert user["full_name"] == "Murugesan S"
    assert client.get("/api/auth/me").json()["role"] == "karigar"


def test_the_summary_is_for_the_karigar_only(client):
    assert client.get("/api/me/summary").status_code == 401
    sign_in(client, "clerk")
    assert client.get("/api/me/summary").status_code == 403
    switch(client, "finance")
    assert client.get("/api/me/summary").status_code == 403


def test_the_summary_shows_only_the_karigars_own_gold(client):
    sign_in_karigar(client)
    body = client.get("/api/me/summary").json()
    assert body["karigar"] == "Murugesan S"
    assert body["balance_g"] == "5.267"
    assert body["open_jobs"] == 0
    assert body["truncated"] is False
    assert [j["job_no"] for j in body["jobs"]] == ["JOB-1041", "JOB-1019"]
    assert all(j["unexplained_g"] is None and j["review"] is None for j in body["jobs"])
    assert len(body["entries"]) == 6
    assert [e["txn_no"] for e in body["entries"]][:3] == ["TX-30438", "TX-30437", "TX-30411"]
    first = body["entries"][0]
    assert first["kind"] == "RECEIPT_SCRAP"
    assert first["change_g"] == "-3.023"
    assert first["fine_weight_g"] == "3.023"
    assert first["job_no"] == "JOB-1041"
    assert first["category"] == "Necklace"
    assert "Selvam" not in str(body)


def test_the_summary_follows_new_activity(client):
    sign_in(client, "clerk")
    assert client.post("/api/issues", json=issue_body(client)).status_code == 201
    client.post("/api/auth/logout")
    sign_in_karigar(client)
    body = client.get("/api/me/summary").json()
    assert body["balance_g"] == "115.187"
    assert body["open_jobs"] == 1
    assert body["entries"][0]["kind"] == "ISSUE"
    assert body["entries"][0]["change_g"] == "+109.920"


def test_a_karigar_is_locked_out_of_every_staff_endpoint(client):
    sign_in_karigar(client)
    allowed = ("/api/auth/", "/api/me/", "/api/health")
    methods = {"get", "post", "put", "patch", "delete"}
    checked = 0
    for template, operations in app.openapi()["paths"].items():
        if not template.startswith("/api/") or template.startswith(allowed):
            continue
        path = re.sub(r"\{[^}]+\}", "1", template)
        for method in operations:
            if method not in methods:
                continue
            response = client.request(method.upper(), path, json={})
            assert response.status_code == 403, (method, template, response.status_code)
            checked += 1
    assert checked >= 25


def test_a_karigar_login_must_point_at_a_karigar(engine):
    with Session(engine) as session:
        session.add(User(username="x1", full_name="X", password_hash="h", role="karigar"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            User(username="x2", full_name="X", password_hash="h",
                 role="issue_clerk", karigar_id=1)
        )
        with pytest.raises(IntegrityError):
            session.commit()