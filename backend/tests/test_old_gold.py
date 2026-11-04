from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger import today_ist
from app.models import AuditLog
from tests.test_corrections import switch
from tests.test_karigars import sign_in
from tests.test_reading_checks import make_reading, reading_row


def body(**over):
    data = {
        "bill_no": "EXB-2026-0500",
        "customer_name": "Test Customer",
        "gross_weight": "10.000",
        "deduction_weight": "0",
        "purity": "91.60",
        "rate_per_g": "12500.00",
        "payment_mode": "BANK_TRANSFER",
    }
    data.update(over)
    return data


def create(client, **over):
    return client.post("/api/old-gold", json=body(**over))


def listing(client, **params):
    response = client.get("/api/old-gold", params=params)
    assert response.status_code == 200
    return response.json()


def total_stock(client, **params):
    response = client.get("/api/stock/statement", params=params)
    assert response.status_code == 200
    return response.json()["total_g"]


# --- access -----------------------------------------------------------------------

def test_endpoints_need_sign_in(client):
    assert client.get("/api/old-gold").status_code == 401
    assert client.get("/api/old-gold/OG-5001").status_code == 401
    assert create(client).status_code == 401
    assert client.post("/api/old-gold/OG-5001/void", json={"reason": "Wrong bill"}).status_code == 401


def test_only_the_clerk_can_record(client):
    sign_in(client, "finance")
    assert create(client).status_code == 403


def test_only_the_finance_head_can_void(client):
    sign_in(client, "clerk")
    assert client.post("/api/old-gold/OG-5001/void", json={"reason": "Wrong bill"}).status_code == 403


# --- recording --------------------------------------------------------------------

def test_a_purchase_is_recorded_with_server_side_figures(client, engine):
    sign_in(client, "clerk")
    response = create(client, note="  First   lot ")
    assert response.status_code == 201
    p = response.json()
    assert p["og_no"] == "OG-5004"
    assert p["entry_date"] == today_ist().isoformat()
    assert p["bill_no"] == "EXB-2026-0500"
    assert p["gross_weight_g"] == "10.000"
    assert p["deduction_g"] == "0.000"
    assert p["net_weight_g"] == "10.000"
    assert p["purity_pct"] == "91.60"
    assert p["fine_weight_g"] == "9.160"
    assert p["rate_per_g"] == "12500.00"
    assert p["value"] == "114500.00"
    assert p["payment_label"] == "Bank transfer"
    assert p["high_value"] is False
    assert p["pan"] is None
    assert p["needs_review"] is None
    assert p["note"] == "First lot"
    assert p["recorded_by"] == "Demo Issue Clerk"
    assert p["voided"] is False
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "old_gold.created" in actions


def test_deductions_come_off_before_purity(client):
    sign_in(client, "clerk")
    p = create(client, deduction_weight="0.500").json()
    assert p["net_weight_g"] == "9.500"
    assert p["fine_weight_g"] == "8.702"
    assert p["value"] == "108775.00"


def test_numbers_are_tidied(client):
    sign_in(client, "clerk")
    p = create(client, bill_no=" exb-2026-0501 ", customer_name="  Test    Customer ").json()
    assert p["bill_no"] == "EXB-2026-0501"
    assert p["customer_name"] == "Test Customer"


# --- PAN and payment mode ------------------------------------------------------------

def test_a_high_value_purchase_needs_a_pan(client):
    sign_in(client, "clerk")
    response = create(client, gross_weight="20.000")
    assert response.status_code == 422
    assert "PAN" in response.json()["detail"]


def test_the_pan_is_stored_uppercase_and_masked_for_the_clerk(client, engine):
    sign_in(client, "clerk")
    response = create(client, gross_weight="20.000", pan=" abcde1234f ")
    assert response.status_code == 201
    p = response.json()
    assert p["value"] == "229000.00"
    assert p["high_value"] is True
    assert p["pan"] == "XXXXXX234F"
    assert p["pan_masked"] is True
    with Session(engine) as session:
        details = list(session.scalars(select(AuditLog.detail).where(AuditLog.action == "old_gold.created")))
    assert all("ABCDE" not in d for d in details)


def test_the_threshold_boundary(client):
    sign_in(client, "clerk")
    just_under = create(client, bill_no="EXB-LOW-1", gross_weight="15.999", purity="100")
    assert just_under.status_code == 201
    assert just_under.json()["value"] == "199987.50"
    at_limit = create(client, bill_no="EXB-AT-1", gross_weight="16.000", purity="100")
    assert at_limit.status_code == 422
    with_pan = create(client, bill_no="EXB-AT-2", gross_weight="16.000", purity="100", pan="ABCDE1234F")
    assert with_pan.status_code == 201
    assert with_pan.json()["value"] == "200000.00"


@pytest.mark.parametrize("pan", ["ABC", "ABCDE12345", "1234567890", "ABCD1234FG"])
def test_a_malformed_pan_is_rejected_even_on_small_purchases(client, pan):
    sign_in(client, "clerk")
    assert create(client, pan=pan).status_code == 422


def test_payment_mode_is_required_and_checked(client):
    sign_in(client, "clerk")
    assert create(client, payment_mode="BARTER").status_code == 422
    data = body()
    del data["payment_mode"]
    assert client.post("/api/old-gold", json=data).status_code == 422


# --- validation ----------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["abc", "0", "0.000", "-1", "1.2345", "2000.001", ""])
def test_bad_gross_weights_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert create(client, gross_weight=bad).status_code == 422


@pytest.mark.parametrize("bad", ["10.000", "11", "abc", "-1", "1.2345"])
def test_bad_deductions_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert create(client, deduction_weight=bad).status_code == 422


@pytest.mark.parametrize("bad", ["0", "100.01", "abc", "-5", "91.605"])
def test_bad_purities_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert create(client, purity=bad).status_code == 422


@pytest.mark.parametrize("bad", ["0", "abc", "-1", "12500.001", "100000.01", ""])
def test_bad_rates_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert create(client, rate_per_g=bad).status_code == 422


def test_json_numbers_are_rejected(client):
    sign_in(client, "clerk")
    assert create(client, gross_weight=10.5).status_code == 422
    assert create(client, rate_per_g=12500).status_code == 422


@pytest.mark.parametrize("bad", ["A", "AB", "bad bill!", "-ABC", "x" * 31])
def test_bad_bill_references_are_rejected(client, bad):
    sign_in(client, "clerk")
    assert create(client, bill_no=bad).status_code == 422


def test_a_blank_customer_name_is_rejected(client):
    sign_in(client, "clerk")
    assert create(client, customer_name="   ").status_code == 422


def test_unknown_fields_are_rejected(client):
    sign_in(client, "clerk")
    assert create(client, fine_weight="9.160").status_code == 422


def test_date_rules(client):
    sign_in(client, "clerk")
    today = today_ist()
    assert create(client, bill_no="EXB-D-1", entry_date=(today + timedelta(days=1)).isoformat()).status_code == 422
    assert create(client, bill_no="EXB-D-2", entry_date=(today - timedelta(days=8)).isoformat()).status_code == 422
    ok = create(client, bill_no="EXB-D-3", entry_date=(today - timedelta(days=7)).isoformat())
    assert ok.status_code == 201


# --- one record per bill -------------------------------------------------------------

def test_a_bill_can_only_be_recorded_once(client):
    sign_in(client, "clerk")
    assert create(client).status_code == 201
    again = create(client, bill_no="exb-2026-0500")
    assert again.status_code == 409
    assert "OG-5004" in again.json()["detail"]


def test_a_voided_bill_can_be_recorded_again(client):
    sign_in(client, "clerk")
    first = create(client).json()["og_no"]
    switch(client, "finance")
    assert client.post(f"/api/old-gold/{first}/void", json={"reason": "Wrong weight"}).status_code == 200
    switch(client, "clerk")
    assert create(client).status_code == 201


# --- photo readings --------------------------------------------------------------------

def test_matching_photo_readings_are_accepted(client, engine):
    sign_in(client, "clerk")
    w = make_reading(engine, "WEIGHT", "10.000")
    p = make_reading(engine, "PURITY", "91.60")
    response = create(client, weight_reading_id=w, purity_reading_id=p)
    assert response.status_code == 201
    og_no = response.json()["og_no"]
    for reading_id in (w, p):
        row = reading_row(engine, reading_id)
        assert row.status == "ACCEPTED"
        assert row.txn_no == og_no


def test_a_mismatch_with_the_photo_blocks_the_save(client, engine):
    sign_in(client, "clerk")
    p = make_reading(engine, "PURITY", "84.50")
    assert create(client, purity_reading_id=p).status_code == 409
    assert reading_row(engine, p).status == "PENDING"
    assert len(listing(client)) == 3


def test_a_mismatch_can_be_overridden_with_a_reason(client, engine):
    sign_in(client, "clerk")
    p = make_reading(engine, "PURITY", "84.50")
    response = create(client, purity_reading_id=p, purity_override_reason="Meter printout was smudged")
    assert response.status_code == 201
    assert reading_row(engine, p).status == "CORRECTED"


# --- listing and detail ----------------------------------------------------------------

def test_the_seeded_list_is_newest_first_with_masked_pans(client):
    sign_in(client, "clerk")
    rows = listing(client)
    assert [r["og_no"] for r in rows] == ["OG-5003", "OG-5002", "OG-5001"]
    assert [r["pan"] for r in rows] == ["XXXXXX234F", None, "XXXXXX678K"]
    assert all(r["needs_review"] is None for r in rows)


def test_the_seeded_figures(client):
    sign_in(client, "clerk")
    rows = {r["og_no"]: r for r in listing(client)}
    assert (rows["OG-5001"]["fine_weight_g"], rows["OG-5001"]["value"]) == ("20.703", "258787.50")
    assert (rows["OG-5002"]["fine_weight_g"], rows["OG-5002"]["value"]) == ("6.232", "77900.00")
    assert (rows["OG-5003"]["net_weight_g"], rows["OG-5003"]["fine_weight_g"], rows["OG-5003"]["value"]) == (
        "50.750", "46.487", "581087.50",
    )


def test_the_finance_head_sees_review_flags(client):
    sign_in(client, "finance")
    flags = {r["og_no"]: r["needs_review"] for r in listing(client)}
    assert flags == {"OG-5001": False, "OG-5002": False, "OG-5003": True}
    assert all(r["pan"] is None or r["pan_masked"] for r in listing(client))


def test_the_list_can_be_searched_by_bill(client):
    sign_in(client, "clerk")
    assert [r["og_no"] for r in listing(client, bill="0419")] == ["OG-5002"]
    assert listing(client, bill="nothing-like-this") == []
    assert len(listing(client, bill="%")) == 0


def test_detail_shows_the_full_pan_to_the_finance_head_only(client):
    sign_in(client, "finance")
    detail = client.get("/api/old-gold/og-5003").json()
    assert detail["pan"] == "ABCDE1234F"
    assert detail["pan_masked"] is False
    switch(client, "clerk")
    masked = client.get("/api/old-gold/OG-5003").json()
    assert masked["pan"] == "XXXXXX234F"
    assert masked["pan_masked"] is True


def test_unknown_purchase_returns_404(client):
    sign_in(client, "finance")
    assert client.get("/api/old-gold/OG-9999").status_code == 404
    assert client.post("/api/old-gold/OG-9999/void", json={"reason": "Wrong bill"}).status_code == 404


# --- voiding -----------------------------------------------------------------------------

def test_voiding_records_the_reason_and_cannot_be_repeated(client, engine):
    sign_in(client, "finance")
    response = client.post("/api/old-gold/OG-5002/void", json={"reason": "  Wrong   customer "})
    assert response.status_code == 200
    assert response.json()["voided"] is True
    assert response.json()["void_reason"] == "Wrong customer"
    assert response.json()["needs_review"] is False
    assert client.post("/api/old-gold/OG-5002/void", json={"reason": "Again please"}).status_code == 409
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "old_gold.voided" in actions


@pytest.mark.parametrize("bad", [{}, {"reason": "no"}, {"reason": "     "}, {"reason": "x" * 151}, {"reason": "Wrong bill", "x": 1}])
def test_bad_void_reasons_are_rejected(client, bad):
    sign_in(client, "finance")
    assert client.post("/api/old-gold/OG-5002/void", json=bad).status_code == 422


# --- the stock statement -------------------------------------------------------------------

def test_old_gold_is_part_of_total_stock_from_its_date(client):
    sign_in(client, "finance")
    assert total_stock(client, as_of="2026-10-27") == "2500.000"
    assert total_stock(client, as_of="2026-10-28") == "2520.703"
    assert total_stock(client, as_of="2026-10-31") == "2526.935"
    assert total_stock(client, as_of="2026-11-02") == "2573.422"


def test_a_new_purchase_adds_to_todays_stock(client):
    sign_in(client, "clerk")
    assert create(client).status_code == 201
    switch(client, "finance")
    assert total_stock(client) == "2582.582"


def test_a_void_changes_stock_from_today_and_not_before(client):
    sign_in(client, "finance")
    assert client.post("/api/old-gold/OG-5003/void", json={"reason": "Recorded twice"}).status_code == 200
    assert total_stock(client, as_of="2026-11-02") == "2573.422"
    assert total_stock(client) == "2526.935"