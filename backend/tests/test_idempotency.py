import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, IdempotencyKey, User
from app.routers.ledger import IssueIn
from tests.test_issues import issue_body
from tests.test_jobs import receipt_body
from tests.test_karigars import by_name, sign_in
from tests.test_old_gold import body as og_body
from tests.test_old_gold import listing as og_listing
from tests.test_reading_checks import make_reading, reading_row

KEY = "retry-key-000000000001"
OTHER = "retry-key-000000000002"


def post(client, path, body, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(path, json=body, headers=headers)


def balance(client):
    karigar_id = by_name(client, "Murugesan S")["id"]
    return client.get(f"/api/karigars/{karigar_id}/balance").json()["balance_g"]


def count_actions(engine, action):
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )


# --- issues ---------------------------------------------------------------------

def test_a_repeated_issue_is_recorded_once(client, engine):
    sign_in(client, "clerk")
    data = issue_body(client)
    first = post(client, "/api/issues", data, KEY)
    second = post(client, "/api/issues", data, KEY)
    assert first.status_code == 201
    assert "idempotent-replay" not in first.headers
    assert second.status_code == 201
    assert second.headers["idempotent-replay"] == "true"
    assert second.json()["txn_no"] == first.json()["txn_no"]
    assert second.json()["job_no"] == first.json()["job_no"]
    assert second.json()["fine_weight_g"] == "109.920"
    assert balance(client) == "115.187"
    assert count_actions(engine, "issue.created") == 1


def test_without_a_key_every_request_is_recorded(client):
    sign_in(client, "clerk")
    data = issue_body(client)
    assert post(client, "/api/issues", data).status_code == 201
    assert post(client, "/api/issues", data).status_code == 201
    assert balance(client) == "225.107"


def test_the_same_key_with_a_different_request_is_refused(client):
    sign_in(client, "clerk")
    assert post(client, "/api/issues", issue_body(client), KEY).status_code == 201
    other = post(client, "/api/issues", issue_body(client, gross_weight="10.000"), KEY)
    assert other.status_code == 422
    assert "different request" in other.json()["detail"]
    assert balance(client) == "115.187"


def test_a_key_cannot_be_reused_for_another_kind_of_entry(client):
    sign_in(client, "clerk")
    assert post(client, "/api/issues", issue_body(client), KEY).status_code == 201
    assert post(client, "/api/receipts", receipt_body(), KEY).status_code == 422


@pytest.mark.parametrize("bad", ["short", "has spaces in the key!!", "x" * 65, "bad/key/0000000000000"])
def test_malformed_keys_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert post(client, "/api/issues", issue_body(client), bad).status_code == 422


def test_a_failed_attempt_is_not_remembered(client):
    sign_in(client, "clerk")
    assert post(client, "/api/issues", issue_body(client, gross_weight="abc"), KEY).status_code == 422
    assert post(client, "/api/issues", issue_body(client), KEY).status_code == 201


def test_a_key_stored_by_an_earlier_attempt_is_honoured(client, engine):
    sign_in(client, "clerk")
    data = issue_body(client)
    digest = hashlib.sha256(IssueIn(**data).model_dump_json().encode()).hexdigest()
    with Session(engine) as session:
        user_id = session.scalar(select(User.id).where(User.username == "clerk"))
        session.add(IdempotencyKey(user_id=user_id, key=KEY, scope="ISSUE",
                                   request_hash=digest, ref="TX-30411"))
        session.commit()
    response = post(client, "/api/issues", data, KEY)
    assert response.status_code == 201
    assert response.json()["txn_no"] == "TX-30411"
    assert response.headers["idempotent-replay"] == "true"
    assert balance(client) == "5.267"


# --- receipts -----------------------------------------------------------------------

def test_a_repeated_receipt_returns_the_original_even_when_nothing_is_outstanding(client):
    sign_in(client, "clerk")
    data = receipt_body(gross_weight="75.000")
    first = post(client, "/api/receipts", data, KEY)
    assert first.status_code == 201
    assert first.json()["job"]["outstanding_g"] == "0.000"
    replay = post(client, "/api/receipts", data, KEY)
    assert replay.status_code == 201
    assert replay.headers["idempotent-replay"] == "true"
    assert replay.json()["txn_no"] == first.json()["txn_no"]
    assert replay.json()["huid"] == "AB12CD"
    # Without the key it is a genuinely new request, and it now fails on its own merits.
    other = post(client, "/api/receipts", receipt_body(gross_weight="75.000", huid="ZZ99YY"))
    assert other.status_code == 422
    assert "outstanding" in other.json()["detail"]


def test_a_repeat_does_not_trip_over_a_used_photo_reading(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000")
    data = issue_body(client, weight_reading_id=w)
    first = post(client, "/api/issues", data, KEY)
    assert first.status_code == 201
    assert reading_row(engine, w).status == "ACCEPTED"
    replay = post(client, "/api/issues", data, KEY)
    assert replay.status_code == 201
    assert replay.json()["txn_no"] == first.json()["txn_no"]
    assert balance(client) == "115.187"


# --- old gold -----------------------------------------------------------------------

def test_a_repeated_old_gold_purchase_is_recorded_once(client):
    sign_in(client, "clerk")
    data = og_body()
    first = post(client, "/api/old-gold", data, OTHER)
    second = post(client, "/api/old-gold", data, OTHER)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.headers["idempotent-replay"] == "true"
    assert second.json()["og_no"] == first.json()["og_no"]
    assert len(og_listing(client)) == 4