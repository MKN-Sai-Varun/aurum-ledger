from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Reading, User
from tests.test_issues import issue_body
from tests.test_jobs import receipt_body
from tests.test_karigars import by_name, sign_in


def user_id(engine, username):
    with Session(engine) as session:
        return session.scalar(select(User.id).where(User.username == username))


def make_reading(engine, target, value, *, user="clerk", age_minutes=0, status="PENDING",
                 source="GEMINI", confirmed=None, reason=None, txn_no=None):
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        reading = Reading(
            user_id=user_id(engine, user),
            target=target,
            source=source,
            value_text=value,
            image_sha256="0" * 64,
            status=status,
            confirmed_text=confirmed,
            override_reason=reason,
            txn_no=txn_no,
            created_at=now - timedelta(minutes=age_minutes),
            resolved_at=now if status != "PENDING" else None,
        )
        session.add(reading)
        session.commit()
        return reading.id


def reading_row(engine, reading_id):
    with Session(engine) as session:
        return session.get(Reading, reading_id)


def audit_details(engine, action):
    with Session(engine) as session:
        return list(session.scalars(select(AuditLog.detail).where(AuditLog.action == action)))


def issue(client, **extra):
    return client.post("/api/issues", json=issue_body(client, **extra))


def murugesan_balance(client):
    karigar_id = by_name(client, "Murugesan S")["id"]
    return client.get(f"/api/karigars/{karigar_id}/balance").json()["balance_g"]


# --- issue entries -------------------------------------------------------------

def test_matching_readings_are_accepted(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000")
    p = make_reading(engine, "PURITY", "91.60")
    response = issue(client, weight_reading_id=w, purity_reading_id=p)
    assert response.status_code == 201
    txn = response.json()["txn_no"]
    for reading_id, typed in ((w, "120.000"), (p, "91.60")):
        row = reading_row(engine, reading_id)
        assert row.status == "ACCEPTED"
        assert row.confirmed_text == typed
        assert row.override_reason is None
        assert row.txn_no == txn
        assert row.resolved_at is not None
    assert len(audit_details(engine, "reading.accepted")) == 2


def test_a_mismatch_blocks_the_save_and_saves_nothing(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "112.450")
    response = issue(client, weight_reading_id=w)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "120.000" in detail and "112.450" in detail
    assert reading_row(engine, w).status == "PENDING"
    assert murugesan_balance(client) == "5.267"


def test_a_purity_mismatch_blocks_the_save(client, engine):
    sign_in(client, "clerk")
    p = make_reading(engine, "PURITY", "92.00")
    response = issue(client, purity_reading_id=p)
    assert response.status_code == 409
    assert "purity" in response.json()["detail"]


def test_an_override_with_a_reason_is_recorded_as_corrected(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "112.450")
    response = issue(
        client, weight_reading_id=w, weight_override_reason="  Display was   dirty, checked by eye "
    )
    assert response.status_code == 201
    row = reading_row(engine, w)
    assert row.status == "CORRECTED"
    assert row.confirmed_text == "120.000"
    assert row.override_reason == "Display was dirty, checked by eye"
    detail = audit_details(engine, "reading.corrected")[0]
    assert "photo 112.450" in detail and "entered 120.000" in detail and "dirty" in detail


def test_a_too_short_reason_is_refused(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "112.450")
    response = issue(client, weight_reading_id=w, weight_override_reason="no")
    assert response.status_code == 422
    assert reading_row(engine, w).status == "PENDING"


def test_a_reason_is_ignored_when_the_values_match(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000")
    response = issue(client, weight_reading_id=w, weight_override_reason="Checked it twice")
    assert response.status_code == 201
    row = reading_row(engine, w)
    assert row.status == "ACCEPTED"
    assert row.override_reason is None


def test_a_reason_without_a_reading_is_rejected(client):
    sign_in(client, "clerk")
    assert issue(client, weight_override_reason="Checked by eye").status_code == 422


def test_a_reading_can_only_be_used_once(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000")
    assert issue(client, weight_reading_id=w).status_code == 201
    again = issue(client, weight_reading_id=w)
    assert again.status_code == 409
    assert "already been used" in again.json()["detail"]


def test_another_clerks_reading_is_refused(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000", user="finance")
    response = issue(client, weight_reading_id=w)
    assert response.status_code == 422
    assert "wasn't found" in response.json()["detail"]


def test_a_reading_for_the_wrong_field_is_refused(client, engine):
    sign_in(client, "clerk")
    p = make_reading(engine, "PURITY", "91.60")
    assert issue(client, weight_reading_id=p).status_code == 422


def test_an_old_reading_is_refused(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "120.000", age_minutes=31)
    response = issue(client, weight_reading_id=w)
    assert response.status_code == 422
    assert "too old" in response.json()["detail"]


def test_a_reading_with_no_value_cannot_confirm_anything(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", None, source="NONE")
    response = issue(client, weight_reading_id=w)
    assert response.status_code == 422
    assert "no value" in response.json()["detail"]


def test_an_unknown_reading_is_refused(client):
    sign_in(client, "clerk")
    assert issue(client, weight_reading_id=9999).status_code == 422


def test_manual_entry_without_readings_still_works(client):
    sign_in(client, "clerk")
    assert issue(client).status_code == 201


# --- receipts ----------------------------------------------------------------------

def receipt(client, **extra):
    return client.post("/api/receipts", json=receipt_body(**extra))


def test_a_receipt_reading_is_accepted_after_normalising(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "70.500")
    response = receipt(client, gross_weight="70.5", weight_reading_id=w)
    assert response.status_code == 201
    row = reading_row(engine, w)
    assert row.status == "ACCEPTED"
    assert row.confirmed_text == "70.500"
    assert row.txn_no == response.json()["txn_no"]


def test_a_receipt_mismatch_is_blocked(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "70.000")
    response = receipt(client, gross_weight="70.500", weight_reading_id=w)
    assert response.status_code == 409
    assert reading_row(engine, w).status == "PENDING"


def test_a_failed_save_does_not_use_up_the_reading(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "80.000")
    response = receipt(client, gross_weight="80.000", weight_reading_id=w)
    assert response.status_code == 422
    assert reading_row(engine, w).status == "PENDING"
    assert response.json()["detail"].startswith("That is")


# --- the finance summary -------------------------------------------------------------

def test_summary_is_finance_only(client):
    assert client.get("/api/readings/summary").status_code == 401
    sign_in(client, "clerk")
    assert client.get("/api/readings/summary").status_code == 403


def test_summary_with_no_readings(client):
    sign_in(client, "finance")
    body = client.get("/api/readings/summary").json()
    assert body["total"] == 0
    assert body["correction_rate_pct"] is None
    assert body["recent_corrections"] == []


def test_summary_counts_and_correction_rate(client, engine):
    for _ in range(3):
        make_reading(engine, "WEIGHT", "1.000", status="ACCEPTED", confirmed="1.000", txn_no="TX-1")
    make_reading(engine, "PURITY", "91.60", status="CORRECTED", confirmed="92.00",
                 reason="Display was smudged", txn_no="TX-2", source="TESSERACT")
    make_reading(engine, "WEIGHT", "2.000")
    make_reading(engine, "WEIGHT", None, source="NONE")
    sign_in(client, "finance")
    body = client.get("/api/readings/summary").json()
    assert body["total"] == 6
    assert body["accepted"] == 3
    assert body["corrected"] == 1
    assert body["unused"] == 2
    assert body["unreadable"] == 1
    assert body["correction_rate_pct"] == "25.0"
    assert body["by_source"] == {"GEMINI": 4, "TESSERACT": 1, "NONE": 1}
    recent = body["recent_corrections"]
    assert len(recent) == 1
    assert recent[0]["txn_no"] == "TX-2"
    assert recent[0]["read_value"] == "91.60"
    assert recent[0]["entered_value"] == "92.00"
    assert recent[0]["reason"] == "Display was smudged"
    assert recent[0]["by"] == "Demo Issue Clerk"