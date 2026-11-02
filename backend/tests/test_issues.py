from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger import today_ist
from app.models import AuditLog, Job, Karigar, LedgerEntry
from tests.test_karigars import by_name, category_id, sign_in


def issue_body(client, karigar="Murugesan S", category="Necklace", **overrides):
    body = {
        "karigar_id": by_name(client, karigar)["id"],
        "category_id": category_id(client, category),
        "gross_weight": "120.000",
        "purity": "91.60",
    }
    body.update(overrides)
    return body


def test_clerk_issues_and_gets_a_slip(client):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client))
    assert response.status_code == 201
    slip = response.json()
    assert slip["karigar"] == "Murugesan S"
    assert slip["category"] == "Necklace"
    assert slip["job_no"] == "JOB-1047"
    assert slip["txn_no"].startswith("TX-")
    assert slip["gross_weight_g"] == "120.000"
    assert slip["purity_pct"] == "91.60"
    assert slip["fine_weight_g"] == "109.920"
    assert slip["allowed_wastage_pct"] == "3.00"
    assert slip["allowed_wastage_g"] == "3.298"
    assert slip["balance_g"] == "115.187"
    assert slip["issued_by"] == "Demo Issue Clerk"


def test_issue_writes_one_ledger_entry_and_an_audit_row(client, engine):
    sign_in(client, "clerk")
    slip = client.post("/api/issues", json=issue_body(client)).json()
    with Session(engine) as session:
        entry = session.scalar(
            select(LedgerEntry).where(LedgerEntry.txn_no == slip["txn_no"])
        )
        job = session.get(Job, entry.job_id)
        actions = list(session.scalars(select(AuditLog.action)))
    assert entry.kind == "ISSUE"
    assert entry.gross_mg == 120000
    assert entry.fine_mg == 109920
    assert entry.balance_delta_mg == 109920
    assert entry.wastage_hundredths == 300
    assert job.status == "OPEN"
    assert job.job_no == slip["job_no"]
    assert "issue.created" in actions


def test_only_the_issue_clerk_can_issue(client):
    anonymous = {
        "karigar_id": 1,
        "category_id": 1,
        "gross_weight": "1.000",
        "purity": "91.60",
    }
    assert client.post("/api/issues", json=anonymous).status_code == 401
    sign_in(client, "finance")
    assert client.post("/api/issues", json=issue_body(client)).status_code == 403


def test_each_issue_gets_new_job_and_transaction_numbers(client):
    sign_in(client, "clerk")
    first = client.post("/api/issues", json=issue_body(client)).json()
    second = client.post(
        "/api/issues", json=issue_body(client, gross_weight="10.000")
    ).json()
    assert first["job_no"] == "JOB-1047"
    assert second["job_no"] == "JOB-1048"
    assert int(second["txn_no"][3:]) == int(first["txn_no"][3:]) + 1
    assert second["balance_g"] == "124.347"


def test_slip_can_be_fetched_again(client):
    sign_in(client, "clerk")
    created = client.post("/api/issues", json=issue_body(client)).json()
    fetched = client.get(f"/api/issues/{created['txn_no']}")
    assert fetched.status_code == 200
    assert fetched.json()["txn_no"] == created["txn_no"]
    assert fetched.json()["fine_weight_g"] == "109.920"


def test_unknown_issue_and_receipt_numbers_return_404(client):
    sign_in(client, "clerk")
    assert client.get("/api/issues/TX-99999").status_code == 404
    assert client.get("/api/issues/TX-30437").status_code == 404


def test_slip_requires_sign_in(client):
    assert client.get("/api/issues/TX-30411").status_code == 401


def test_inactive_karigar_cannot_be_issued_to(client, engine):
    sign_in(client, "clerk")
    body = issue_body(client)
    with Session(engine) as session:
        session.get(Karigar, body["karigar_id"]).is_active = False
        session.commit()
    assert client.post("/api/issues", json=body).status_code == 409


def test_issue_needs_an_agreed_wastage(client):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, category="Ring"))
    assert response.status_code == 422
    assert "agreed wastage" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "bad", ["abc", "", "0", "0.000", "-5", "1.2345", "1e3", "2000.001"]
)
def test_invalid_weights_are_rejected(client, bad):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, gross_weight=bad))
    assert response.status_code == 422


@pytest.mark.parametrize("bad", ["0", "100.01", "91.605", "abc", "-1"])
def test_invalid_purity_is_rejected(client, bad):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, purity=bad))
    assert response.status_code == 422


def test_weight_and_purity_giving_no_fine_gold_are_rejected(client):
    sign_in(client, "clerk")
    response = client.post(
        "/api/issues", json=issue_body(client, gross_weight="0.001", purity="0.01")
    )
    assert response.status_code == 422


def test_a_json_number_for_weight_is_rejected(client):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, gross_weight=120.5))
    assert response.status_code == 422


def test_client_cannot_send_its_own_fine_weight(client):
    sign_in(client, "clerk")
    response = client.post(
        "/api/issues", json=issue_body(client, fine_weight="999.000")
    )
    assert response.status_code == 422


def test_unknown_karigar_and_category_return_404(client):
    sign_in(client, "clerk")
    assert client.post("/api/issues", json=issue_body(client, karigar_id=9999)).status_code == 404
    assert client.post("/api/issues", json=issue_body(client, category_id=9999)).status_code == 404


def test_date_rules(client):
    sign_in(client, "clerk")
    today = today_ist()
    three_days_ago = (today - timedelta(days=3)).isoformat()
    ok = client.post("/api/issues", json=issue_body(client, entry_date=three_days_ago))
    assert ok.status_code == 201
    assert ok.json()["entry_date"] == three_days_ago
    seven = (today - timedelta(days=7)).isoformat()
    assert client.post("/api/issues", json=issue_body(client, entry_date=seven)).status_code == 201
    tomorrow = (today + timedelta(days=1)).isoformat()
    assert client.post("/api/issues", json=issue_body(client, entry_date=tomorrow)).status_code == 422
    eight = (today - timedelta(days=8)).isoformat()
    assert client.post("/api/issues", json=issue_body(client, entry_date=eight)).status_code == 422


def test_note_is_tidied(client):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, note="  First   lot "))
    assert response.status_code == 201
    assert response.json()["note"] == "First lot"


def test_note_that_is_too_long_is_rejected(client):
    sign_in(client, "clerk")
    response = client.post("/api/issues", json=issue_body(client, note="x" * 201))
    assert response.status_code == 422


def test_the_largest_allowed_issue_is_accepted(client):
    sign_in(client, "clerk")
    response = client.post(
        "/api/issues", json=issue_body(client, gross_weight="2000.000")
    )
    assert response.status_code == 201
    assert response.json()["fine_weight_g"] == "1832.000"


@pytest.mark.parametrize(
    "day, expected",
    [
        ("2026-09-01", "0.000"),
        ("2026-09-02", "54.960"),
        ("2026-09-12", "1.374"),
        ("2026-10-26", "111.294"),
        ("2026-10-27", "5.267"),
    ],
)
def test_balance_as_of_a_date_matches_the_seed(client, day, expected):
    sign_in(client, "clerk")
    karigar_id = by_name(client, "Murugesan S")["id"]
    response = client.get(f"/api/karigars/{karigar_id}/balance", params={"as_of": day})
    assert response.status_code == 200
    assert response.json()["balance_g"] == expected
    assert response.json()["as_of"] == day


def test_balance_defaults_to_today(client):
    sign_in(client, "clerk")
    karigar_id = by_name(client, "Murugesan S")["id"]
    response = client.get(f"/api/karigars/{karigar_id}/balance")
    assert response.status_code == 200
    assert response.json()["balance_g"] == "5.267"


def test_balance_rejects_a_bad_date(client):
    sign_in(client, "clerk")
    karigar_id = by_name(client, "Murugesan S")["id"]
    response = client.get(
        f"/api/karigars/{karigar_id}/balance", params={"as_of": "not-a-date"}
    )
    assert response.status_code == 422


def test_balance_for_an_unknown_karigar_returns_404(client):
    sign_in(client, "clerk")
    assert client.get("/api/karigars/9999/balance").status_code == 404


def test_balance_requires_sign_in(client):
    assert client.get("/api/karigars/1/balance").status_code == 401