import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger import today_ist
from app.models import AuditLog
from tests.test_jobs import receipt_body
from tests.test_karigars import by_name, sign_in

REASON = {"reason": "Wrong weight entered"}


def switch(client, who):
    client.post("/api/auth/logout")
    sign_in(client, who)


def txns(client, job_no):
    entries = client.get(f"/api/jobs/{job_no}").json()["entries"]
    return {e["kind"]: e["txn_no"] for e in entries}


def clerk_receipt(client, **overrides):
    switch(client, "clerk")
    response = client.post("/api/receipts", json=receipt_body(**overrides))
    assert response.status_code == 201
    return response.json()["txn_no"]


def ledger(client, name="Murugesan S", params=None):
    karigar_id = by_name(client, name)["id"]
    return client.get(f"/api/karigars/{karigar_id}/ledger", params=params or {})


# --- reversing entries --------------------------------------------------------

def test_reversal_needs_the_finance_head(client):
    assert client.post("/api/entries/TX-30437/reverse", json=REASON).status_code == 401
    sign_in(client, "clerk")
    assert client.post("/api/entries/TX-30437/reverse", json=REASON).status_code == 403


def test_unknown_entry_returns_404(client):
    sign_in(client, "finance")
    assert client.post("/api/entries/TX-99999/reverse", json=REASON).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reason": "ok"},
        {"reason": "     "},
        {"reason": "x" * 151},
        {"reason": "Wrong weight", "extra": 1},
    ],
)
def test_bad_reasons_are_rejected(client, body):
    sign_in(client, "finance")
    assert client.post("/api/entries/TX-30437/reverse", json=body).status_code == 422


def test_reversing_a_receipt_restores_the_outstanding_gold(client, engine):
    txn = clerk_receipt(client)
    switch(client, "finance")
    response = client.post(f"/api/entries/{txn}/reverse", json=REASON)
    assert response.status_code == 201
    body = response.json()
    assert body["reverses_txn_no"] == txn
    assert body["reversed_kind"] == "RECEIPT_PIECE"
    assert body["entry_date"] == today_ist().isoformat()
    assert body["fine_weight_g"] == "64.120"
    assert body["change_g"] == "+64.120"
    assert body["reason"] == "Wrong weight entered"
    assert body["job"]["outstanding_g"] == "68.700"
    assert body["job"]["status"] == "OPEN"
    ramesh = by_name(client, "Ramesh P")["id"]
    assert client.get(f"/api/karigars/{ramesh}/balance").json()["balance_g"] == "70.532"
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "entry.reversed" in actions


def test_the_transaction_number_is_case_insensitive(client):
    txn = clerk_receipt(client)
    switch(client, "finance")
    assert client.post(f"/api/entries/{txn.lower()}/reverse", json=REASON).status_code == 201


def test_a_reversed_piece_frees_its_huid(client):
    txn = clerk_receipt(client)
    switch(client, "finance")
    assert client.post(f"/api/entries/{txn}/reverse", json=REASON).status_code == 201
    switch(client, "clerk")
    again = client.post("/api/receipts", json=receipt_body())
    assert again.status_code == 201
    assert again.json()["huid"] == "AB12CD"


def test_an_entry_can_only_be_reversed_once(client):
    txn = clerk_receipt(client)
    switch(client, "finance")
    assert client.post(f"/api/entries/{txn}/reverse", json=REASON).status_code == 201
    assert client.post(f"/api/entries/{txn}/reverse", json=REASON).status_code == 409


def test_a_reversal_cannot_be_reversed(client):
    txn = clerk_receipt(client)
    switch(client, "finance")
    reversal = client.post(f"/api/entries/{txn}/reverse", json=REASON).json()["txn_no"]
    assert client.post(f"/api/entries/{reversal}/reverse", json=REASON).status_code == 409


def test_an_issue_with_receipts_cannot_be_reversed(client):
    sign_in(client, "finance")
    issue = txns(client, "JOB-1041")["ISSUE"]
    response = client.post(f"/api/entries/{issue}/reverse", json=REASON)
    assert response.status_code == 409
    assert "receipts" in response.json()["detail"].lower()


def test_reversing_an_issue_closes_the_job(client):
    sign_in(client, "finance")
    issue = txns(client, "JOB-1044")["ISSUE"]
    response = client.post(f"/api/entries/{issue}/reverse", json=REASON)
    assert response.status_code == 201
    body = response.json()
    assert body["reversed_kind"] == "ISSUE"
    assert body["change_g"] == "-68.700"
    job = body["job"]
    assert job["status"] == "CLOSED"
    assert job["closed_on"] == today_ist().isoformat()
    assert job["issued_fine_g"] == "0.000"
    assert job["returned_fine_g"] == "0.000"
    assert job["outstanding_g"] == "0.000"
    assert job["allowed_wastage_g"] == "0.000"
    assert job["review"] is False
    ramesh = by_name(client, "Ramesh P")
    assert ramesh["open_jobs"] == 0
    balance = client.get(f"/api/karigars/{ramesh['id']}/balance").json()["balance_g"]
    assert balance == "1.832"


def test_a_cancelled_job_refuses_receipts(client):
    sign_in(client, "finance")
    issue = txns(client, "JOB-1044")["ISSUE"]
    client.post(f"/api/entries/{issue}/reverse", json=REASON)
    switch(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body()).status_code == 409


def test_receipts_on_closed_jobs_can_be_reversed(client):
    sign_in(client, "finance")
    piece = txns(client, "JOB-1041")["RECEIPT_PIECE"]
    response = client.post(f"/api/entries/{piece}/reverse", json=REASON)
    assert response.status_code == 201
    job = response.json()["job"]
    assert job["status"] == "CLOSED"
    assert job["outstanding_g"] == "106.897"
    assert job["returned_fine_g"] == "3.023"
    assert job["unexplained_g"] == "103.599"
    assert job["review"] is True
    detail = client.get("/api/jobs/JOB-1041").json()
    assert [e["kind"] for e in detail["entries"]] == [
        "ISSUE",
        "RECEIPT_PIECE",
        "RECEIPT_SCRAP",
        "REVERSAL",
    ]


def test_reversal_never_rewrites_history(client):
    sign_in(client, "finance")
    piece = txns(client, "JOB-1041")["RECEIPT_PIECE"]
    assert client.post(f"/api/entries/{piece}/reverse", json=REASON).status_code == 201
    murugesan = by_name(client, "Murugesan S")["id"]
    then = client.get(
        f"/api/karigars/{murugesan}/balance", params={"as_of": "2026-10-27"}
    ).json()["balance_g"]
    now = client.get(f"/api/karigars/{murugesan}/balance").json()["balance_g"]
    assert then == "5.267"
    assert now == "108.271"


# --- the karigar ledger -------------------------------------------------------

def test_ledger_requires_sign_in(client):
    assert client.get("/api/karigars/1/ledger").status_code == 401


def test_unknown_karigar_ledger_returns_404(client):
    sign_in(client, "clerk")
    assert client.get("/api/karigars/9999/ledger").status_code == 404


def test_both_roles_can_read_the_ledger(client):
    sign_in(client, "clerk")
    assert ledger(client).status_code == 200
    switch(client, "finance")
    assert ledger(client).status_code == 200


def test_full_ledger_has_running_balances(client):
    sign_in(client, "clerk")
    body = ledger(client).json()
    assert body["karigar"] == "Murugesan S"
    assert body["opening_balance_g"] == "0.000"
    assert body["closing_balance_g"] == "5.267"
    assert body["truncated"] is False
    assert [row["balance_g"] for row in body["entries"]] == [
        "54.960",
        "2.290",
        "1.374",
        "111.294",
        "8.290",
        "5.267",
    ]
    assert [row["change_g"] for row in body["entries"]] == [
        "+54.960",
        "-52.670",
        "-0.916",
        "+109.920",
        "-103.004",
        "-3.023",
    ]
    assert [row["txn_no"] for row in body["entries"]][-3:] == [
        "TX-30411",
        "TX-30437",
        "TX-30438",
    ]


def test_ledger_from_date_gives_an_opening_balance(client):
    sign_in(client, "clerk")
    body = ledger(client, params={"from": "2026-10-01"}).json()
    assert body["opening_balance_g"] == "1.374"
    assert len(body["entries"]) == 3
    assert body["entries"][0]["change_g"] == "+109.920"
    assert body["closing_balance_g"] == "5.267"


def test_ledger_to_date_stops_the_balance(client):
    sign_in(client, "clerk")
    body = ledger(client, params={"to": "2026-09-12"}).json()
    assert len(body["entries"]) == 3
    assert body["closing_balance_g"] == "1.374"


def test_ledger_rejects_a_reversed_range_and_bad_values(client):
    sign_in(client, "clerk")
    assert ledger(client, params={"from": "2026-10-01", "to": "2026-09-01"}).status_code == 422
    assert ledger(client, params={"from": "not-a-date"}).status_code == 422
    assert ledger(client, params={"limit": 0}).status_code == 422
    assert ledger(client, params={"limit": 501}).status_code == 422


def test_ledger_limit_truncates_but_keeps_the_closing_balance(client):
    sign_in(client, "clerk")
    body = ledger(client, params={"limit": 2}).json()
    assert len(body["entries"]) == 2
    assert body["truncated"] is True
    assert body["closing_balance_g"] == "5.267"


def test_ledger_links_an_entry_to_its_reversal(client):
    sign_in(client, "finance")
    assert client.post("/api/entries/TX-30437/reverse", json=REASON).status_code == 201
    body = ledger(client).json()
    rows = {row["txn_no"]: row for row in body["entries"]}
    original = rows["TX-30437"]
    reversal = body["entries"][-1]
    assert reversal["kind"] == "REVERSAL"
    assert reversal["reverses"] == "TX-30437"
    assert original["reversed_by"] == reversal["txn_no"]
    assert reversal["change_g"] == "+103.004"
    assert reversal["balance_g"] == "108.271"
    assert body["closing_balance_g"] == "108.271"
    assert "TX-30437" in reversal["note"]