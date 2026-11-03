from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.gold_math import parse_weight_g
from app.ledger import today_ist
from app.models import AuditLog
from tests.test_karigars import sign_in


def statement(client, **params):
    response = client.get("/api/stock/statement", params=params)
    assert response.status_code == 200
    return response.json()


def move(client, direction, weight, **extra):
    body = {"direction": direction, "fine_weight": weight}
    body.update(extra)
    return client.post("/api/stock/refiner", json=body)


def test_stock_endpoints_are_finance_only(client):
    for path in ["/api/stock/statement", "/api/stock/entries", "/api/stock/statement.csv"]:
        assert client.get(path).status_code == 401
    sign_in(client, "clerk")
    for path in ["/api/stock/statement", "/api/stock/entries", "/api/stock/statement.csv"]:
        assert client.get(path).status_code == 403
    assert move(client, "SEND", "1.000").status_code == 403


def test_seeded_statement(client):
    sign_in(client, "finance")
    s = statement(client, as_of="2026-11-02")
    assert s["total_g"] == "2500.000"
    assert s["karigars_g"] == "210.908"
    assert s["refiner_g"] == "110.000"
    assert s["vault_g"] == "2179.092"
    assert s["consistent"] is True


def test_statement_lists_what_each_karigar_holds(client):
    sign_in(client, "finance")
    holders = {h["karigar"]: h["balance_g"] for h in statement(client, as_of="2026-11-02")["holders"]}
    assert holders == {
        "Anbu R": "28.213",
        "Dhanapal V": "16.030",
        "Karthik M": "80.150",
        "Murugesan S": "5.267",
        "Ramesh P": "70.532",
        "Selvam K": "10.716",
    }


def test_before_opening_everything_is_zero(client):
    sign_in(client, "finance")
    s = statement(client, as_of="2026-06-30")
    assert (s["total_g"], s["vault_g"], s["karigars_g"], s["refiner_g"]) == (
        "0.000", "0.000", "0.000", "0.000",
    )
    assert s["holders"] == []


def test_refiner_gold_shows_between_send_and_receive(client):
    sign_in(client, "finance")
    assert statement(client, as_of="2026-10-20")["refiner_g"] == "150.000"
    assert statement(client, as_of="2026-10-26")["refiner_g"] == "110.000"


def test_every_gram_is_accounted_for_on_any_day(client):
    sign_in(client, "finance")
    for day in ["2026-06-30", "2026-07-01", "2026-09-15", "2026-10-20", "2026-10-26", "2026-11-02"]:
        s = statement(client, as_of=day)
        parts = sum(parse_weight_g(s[k]) for k in ("vault_g", "karigars_g", "refiner_g"))
        assert parts == parse_weight_g(s["total_g"])


def test_statement_rejects_future_and_bad_dates(client):
    sign_in(client, "finance")
    assert client.get("/api/stock/statement", params={"as_of": "2099-01-01"}).status_code == 422
    assert client.get("/api/stock/statement", params={"as_of": "nope"}).status_code == 422


def test_sending_to_the_refiner(client, engine):
    sign_in(client, "finance")
    response = move(client, "SEND", "100.000", note="  Batch   7 ")
    assert response.status_code == 201
    body = response.json()
    assert body["entry"]["kind"] == "TO_REFINER"
    assert body["entry"]["label"] == "Sent to refiner"
    assert body["entry"]["fine_weight_g"] == "100.000"
    assert body["entry"]["note"] == "Batch 7"
    assert body["entry"]["entry_date"] == today_ist().isoformat()
    assert body["statement"]["refiner_g"] == "210.000"
    assert body["statement"]["vault_g"] == "2079.092"
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "stock.sent_to_refiner" in actions


def test_receiving_everything_back(client):
    sign_in(client, "finance")
    response = move(client, "RECEIVE", "110.000")
    assert response.status_code == 201
    assert response.json()["statement"]["refiner_g"] == "0.000"
    assert response.json()["statement"]["vault_g"] == "2289.092"


def test_cannot_send_more_than_the_vault_holds(client):
    sign_in(client, "finance")
    response = move(client, "SEND", "2200.000")
    assert response.status_code == 422
    assert "vault" in response.json()["detail"]


def test_cannot_receive_more_than_is_at_the_refiner(client):
    sign_in(client, "finance")
    response = move(client, "RECEIVE", "110.001")
    assert response.status_code == 422
    assert "refiner" in response.json()["detail"]


@pytest.mark.parametrize("bad", ["abc", "0", "0.000", "-5", "1.2345", "5000.001", ""])
def test_invalid_weights_are_rejected(client, bad):
    sign_in(client, "finance")
    assert move(client, "SEND", bad).status_code == 422


def test_bad_direction_and_extra_fields_are_rejected(client):
    sign_in(client, "finance")
    assert move(client, "KEEP", "1.000").status_code == 422
    assert move(client, "SEND", "1.000", reason="x").status_code == 422


def test_json_number_for_weight_is_rejected(client):
    sign_in(client, "finance")
    assert client.post(
        "/api/stock/refiner", json={"direction": "SEND", "fine_weight": 5.5}
    ).status_code == 422


def test_movement_date_rules(client):
    sign_in(client, "finance")
    today = today_ist()
    assert move(client, "SEND", "1.000", entry_date=(today + timedelta(days=1)).isoformat()).status_code == 422
    assert move(client, "SEND", "1.000", entry_date=(today - timedelta(days=8)).isoformat()).status_code == 422
    assert move(client, "SEND", "1.000", entry_date=(today - timedelta(days=7)).isoformat()).status_code == 201


def test_entries_are_listed_newest_first(client):
    sign_in(client, "finance")
    rows = client.get("/api/stock/entries").json()
    assert [r["kind"] for r in rows] == ["FROM_REFINER", "TO_REFINER", "OPENING"]
    assert rows[2]["fine_weight_g"] == "2500.000"
    assert rows[0]["by"] == "Demo Finance Head"
    assert client.get("/api/stock/entries", params={"limit": 0}).status_code == 422


def test_csv_export(client):
    sign_in(client, "finance")
    response = client.get("/api/stock/statement.csv", params={"as_of": "2026-11-02"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="aurum-stock-2026-11-02.csv"' in response.headers["content-disposition"]
    lines = response.text.strip().split("\r\n")
    assert lines[0] == "Date,Particulars,Fine gold (g)"
    assert "2026-11-02,Vault,2179.092" in lines
    assert "2026-11-02,With karigar: Selvam K,10.716" in lines
    assert "2026-11-02,At refiner,110.000" in lines
    assert lines[-1] == "2026-11-02,Total stock,2500.000"