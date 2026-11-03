import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger import today_ist
from app.models import AuditLog, LedgerEntry
from tests.test_karigars import by_name, sign_in


def receipt_body(**overrides):
    body = {
        "job_no": "JOB-1044",
        "kind": "PIECE",
        "gross_weight": "70.000",
        "purity": "91.60",
        "huid": "AB12CD",
    }
    body.update(overrides)
    return body


def jobs_by_no(client, **params):
    response = client.get("/api/jobs", params=params)
    assert response.status_code == 200
    return {job["job_no"]: job for job in response.json()}


# --- reading jobs -----------------------------------------------------------

def test_job_endpoints_require_sign_in(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs/JOB-1041").status_code == 401


def test_job_list_counts_and_filters(client):
    sign_in(client, "finance")
    assert len(jobs_by_no(client)) == 14
    assert len(jobs_by_no(client, status="OPEN")) == 4
    assert len(jobs_by_no(client, status="CLOSED")) == 10


def test_job_list_is_newest_first(client):
    sign_in(client, "finance")
    first = client.get("/api/jobs").json()[0]
    assert first["job_no"] == "JOB-1045"


def test_job_list_can_filter_by_karigar(client):
    sign_in(client, "finance")
    ramesh = by_name(client, "Ramesh P")["id"]
    assert set(jobs_by_no(client, karigar_id=ramesh)) == {"JOB-1024", "JOB-1044"}


def test_bad_status_filter_is_rejected(client):
    sign_in(client, "finance")
    assert client.get("/api/jobs", params={"status": "ARCHIVED"}).status_code == 422


def test_review_items_match_the_seed(client):
    sign_in(client, "finance")
    flagged = {no for no, job in jobs_by_no(client).items() if job["review"]}
    assert flagged == {"JOB-1024", "JOB-1027", "JOB-1029", "JOB-1038", "JOB-1041"}


def test_brief_sample_job_detail(client):
    sign_in(client, "finance")
    job = client.get("/api/jobs/JOB-1041").json()
    assert job["karigar"] == "Murugesan S"
    assert job["status"] == "CLOSED"
    assert job["issued_fine_g"] == "109.920"
    assert job["returned_fine_g"] == "106.027"
    assert job["outstanding_g"] == "3.893"
    assert job["allowed_wastage_pct"] == "3.00"
    assert job["allowed_wastage_g"] == "3.298"
    assert job["unexplained_g"] == "0.595"
    assert job["review"] is True
    assert [e["kind"] for e in job["entries"]] == [
        "ISSUE",
        "RECEIPT_PIECE",
        "RECEIPT_SCRAP",
    ]
    assert [e["txn_no"] for e in job["entries"]] == ["TX-30411", "TX-30437", "TX-30438"]
    assert job["entries"][1]["huid"]


def test_loss_within_allowance_is_not_a_review_item(client):
    sign_in(client, "finance")
    job = client.get("/api/jobs/JOB-1003").json()
    assert job["unexplained_g"] == "-0.275"
    assert job["review"] is False


def test_open_job_is_never_flagged(client):
    sign_in(client, "finance")
    job = client.get("/api/jobs/JOB-1044").json()
    assert job["status"] == "OPEN"
    assert job["unexplained_g"] == "66.639"
    assert job["review"] is False


def test_clerk_does_not_see_the_review_fields(client):
    sign_in(client, "clerk")
    job = client.get("/api/jobs/JOB-1041").json()
    assert job["outstanding_g"] == "3.893"
    assert job["allowed_wastage_g"] == "3.298"
    assert job["unexplained_g"] is None
    assert job["review"] is None
    listed = jobs_by_no(client)["JOB-1041"]
    assert listed["review"] is None


def test_unknown_job_returns_404(client):
    sign_in(client, "finance")
    assert client.get("/api/jobs/JOB-9999").status_code == 404


# --- recording receipts -----------------------------------------------------

def test_only_the_issue_clerk_can_record_receipts(client):
    assert client.post("/api/receipts", json=receipt_body()).status_code == 401
    sign_in(client, "finance")
    assert client.post("/api/receipts", json=receipt_body()).status_code == 403


def test_clerk_records_a_finished_piece(client, engine):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body())
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "RECEIPT_PIECE"
    assert body["gross_weight_g"] == "70.000"
    assert body["purity_pct"] == "91.60"
    assert body["fine_weight_g"] == "64.120"
    assert body["huid"] == "AB12CD"
    assert body["entry_date"] == today_ist().isoformat()
    assert body["job"]["status"] == "OPEN"
    assert body["job"]["outstanding_g"] == "4.580"
    assert body["job"]["allowed_wastage_g"] == "2.061"
    assert body["job"]["review"] is None
    with Session(engine) as session:
        entry = session.scalar(
            select(LedgerEntry).where(LedgerEntry.txn_no == body["txn_no"])
        )
        actions = list(session.scalars(select(AuditLog.action)))
    assert entry.balance_delta_mg == -64120
    assert entry.wastage_hundredths == 300
    assert "receipt.created" in actions


def test_receipt_lowers_the_karigar_balance(client):
    sign_in(client, "clerk")
    client.post("/api/receipts", json=receipt_body())
    ramesh = by_name(client, "Ramesh P")["id"]
    balance = client.get(f"/api/karigars/{ramesh}/balance").json()["balance_g"]
    assert balance == "6.412"


def test_scrap_needs_no_huid(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(kind="SCRAP", huid=None))
    assert response.status_code == 201
    assert response.json()["kind"] == "RECEIPT_SCRAP"
    assert response.json()["huid"] is None


def test_filings_are_accepted(client):
    sign_in(client, "clerk")
    response = client.post(
        "/api/receipts", json=receipt_body(kind="FILINGS", huid=None, gross_weight="0.500")
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "RECEIPT_FILINGS"


def test_piece_needs_a_huid(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(huid=None)).status_code == 422


def test_only_pieces_can_carry_a_huid(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(kind="SCRAP")).status_code == 422


@pytest.mark.parametrize("bad", ["AB1", "ABCDEFGHIJKLM", "AB-123"])
def test_invalid_huid_is_rejected(client, bad):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(huid=bad)).status_code == 422


def test_huid_is_tidied(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(huid=" ab12cd "))
    assert response.status_code == 201
    assert response.json()["huid"] == "AB12CD"


def test_duplicate_huid_is_rejected_across_jobs(client):
    sign_in(client, "clerk")
    first = client.post("/api/receipts", json=receipt_body(gross_weight="20.000"))
    assert first.status_code == 201
    second = client.post(
        "/api/receipts",
        json=receipt_body(job_no="JOB-1045", gross_weight="10.000", huid="ab12cd"),
    )
    assert second.status_code == 409


def test_job_number_is_case_insensitive(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(job_no="job-1044"))
    assert response.status_code == 201
    assert response.json()["job"]["job_no"] == "JOB-1044"


def test_cannot_return_more_than_is_outstanding(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(gross_weight="80.000"))
    assert response.status_code == 422
    assert "outstanding" in response.json()["detail"]


def test_returning_exactly_what_is_outstanding_is_allowed(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(gross_weight="75.000"))
    assert response.status_code == 201
    assert response.json()["job"]["outstanding_g"] == "0.000"


def test_unknown_job_returns_404(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(job_no="JOB-9999")).status_code == 404


def test_closed_job_refuses_receipts(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(job_no="JOB-1041")).status_code == 409


@pytest.mark.parametrize("bad", ["abc", "0", "0.000", "-5", "1.2345", "2000.001", ""])
def test_invalid_weights_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(gross_weight=bad)).status_code == 422


@pytest.mark.parametrize("bad", ["0", "100.01", "abc", "91.605"])
def test_invalid_purity_is_rejected(client, bad):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(purity=bad)).status_code == 422


def test_json_number_for_weight_is_rejected(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body(gross_weight=70.5)).status_code == 422


def test_unknown_fields_are_rejected(client):
    sign_in(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(fine_weight="64.120"))
    assert response.status_code == 422


def test_date_rules(client):
    sign_in(client, "clerk")
    today = today_ist().isoformat()
    ok = client.post("/api/receipts", json=receipt_body(entry_date=today))
    assert ok.status_code == 201
    assert ok.json()["entry_date"] == today


def test_future_and_pre_opening_dates_are_rejected(client):
    sign_in(client, "clerk")
    assert client.post(
        "/api/receipts", json=receipt_body(entry_date="2099-01-01")
    ).status_code == 422
    # JOB-1044 was opened on 2026-10-30.
    assert client.post(
        "/api/receipts", json=receipt_body(entry_date="2026-10-29")
    ).status_code == 422


# --- closing jobs -----------------------------------------------------------

def test_only_the_clerk_can_close_a_job(client):
    sign_in(client, "finance")
    assert client.post("/api/jobs/JOB-1044/close").status_code == 403


def test_closing_unknown_job_returns_404(client):
    sign_in(client, "clerk")
    assert client.post("/api/jobs/JOB-9999/close").status_code == 404


def test_close_a_job_once(client, engine):
    sign_in(client, "clerk")
    closed = client.post("/api/jobs/JOB-1044/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["closed_on"] == today_ist().isoformat()
    assert closed.json()["review"] is None
    assert client.post("/api/jobs/JOB-1044/close").status_code == 409
    assert client.post("/api/receipts", json=receipt_body()).status_code == 409
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "job.closed" in actions


def test_closing_with_loss_above_allowance_becomes_a_review_item(client):
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body()).status_code == 201
    assert client.post("/api/jobs/JOB-1044/close").status_code == 200
    client.post("/api/auth/logout")
    sign_in(client, "finance")
    job = client.get("/api/jobs/JOB-1044").json()
    assert job["unexplained_g"] == "2.519"
    assert job["review"] is True