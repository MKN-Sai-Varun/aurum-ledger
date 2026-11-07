import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.domain.gold_math import parse_weight_g
from app.ledger import today_ist
from app.models import AuditLog
from tests.test_corrections import switch
from tests.test_issues import issue_body
from tests.test_jobs import receipt_body
from tests.test_karigars import sign_in
from tests.test_old_gold import body as og_body

NEW_DAY = "2026-11-03"


def mg(signed):
    sign = -1 if signed.startswith("-") else 1
    return sign * parse_weight_g(signed.lstrip("+-"))


def view(client, day):
    response = client.get("/api/closing/day", params={"date": day})
    assert response.status_code == 200
    return response.json()


def lines(data):
    return {m["key"]: m for m in data["movements"]}


def close(client, day, counted, **extra):
    body = {"close_date": day, "counted_vault": counted}
    body.update(extra)
    return client.post("/api/closing/close", json=body)


def assert_adds_up(data):
    effects = [mg(m["effect_g"]) for m in data["movements"]]
    opening = parse_weight_g(data["opening"]["vault_g"])
    closing = parse_weight_g(data["closing"]["vault_g"])
    assert opening + sum(effects) == closing
    assert data["reconciles"] is True


# --- access ------------------------------------------------------------------------------

def test_closing_is_finance_only(client):
    for path in ("/api/closing/day", "/api/closing/history"):
        assert client.get(path).status_code == 401
    assert close(client, NEW_DAY, "1.000").status_code == 401
    sign_in(client, "clerk")
    for path in ("/api/closing/day", "/api/closing/history"):
        assert client.get(path).status_code == 403
    assert close(client, NEW_DAY, "1.000").status_code == 403


# --- the day view ---------------------------------------------------------------------------

def test_a_day_with_old_gold_bought(client):
    sign_in(client, "finance")
    data = view(client, "2026-11-02")
    assert data["opening"]["vault_g"] == "2206.027"
    assert data["closing"]["vault_g"] == "2252.514"
    assert data["closing"]["total_g"] == "2573.422"
    assert data["closing"]["karigars_g"] == "210.908"
    assert data["closing"]["refiner_g"] == "110.000"
    found = lines(data)
    assert (found["old_gold"]["count"], found["old_gold"]["effect_g"]) == (1, "+46.487")
    assert found["issued"]["count"] == 0 and found["issued"]["effect_g"] == "0.000"
    assert_adds_up(data)


def test_a_day_with_returns(client):
    sign_in(client, "finance")
    data = view(client, "2026-11-01")
    assert (lines(data)["returned"]["count"], lines(data)["returned"]["effect_g"]) == (1, "+9.160")
    assert (data["opening"]["vault_g"], data["closing"]["vault_g"]) == ("2196.867", "2206.027")
    assert_adds_up(data)
    two = view(client, "2026-10-27")
    assert (lines(two)["returned"]["count"], lines(two)["returned"]["effect_g"]) == (2, "+106.027")


def test_a_day_with_an_issue_and_old_gold(client):
    sign_in(client, "finance")
    data = view(client, "2026-10-31")
    found = lines(data)
    assert (found["issued"]["count"], found["issued"]["effect_g"]) == (1, "-27.480")
    assert (found["old_gold"]["count"], found["old_gold"]["effect_g"]) == (1, "+6.232")
    assert (data["opening"]["vault_g"], data["closing"]["vault_g"]) == ("2218.115", "2196.867")
    assert data["closed"] is None
    assert_adds_up(data)


def test_refiner_movements_appear_on_their_days(client):
    sign_in(client, "finance")
    sent = view(client, "2026-10-15")
    assert lines(sent)["to_refiner"]["effect_g"] == "-150.000"
    received = view(client, "2026-10-25")
    assert lines(received)["from_refiner"]["effect_g"] == "+40.000"
    assert_adds_up(sent)
    assert_adds_up(received)


def test_the_opening_stock_day(client):
    sign_in(client, "finance")
    data = view(client, "2026-07-01")
    assert lines(data)["opening_added"]["effect_g"] == "+2500.000"
    assert (data["opening"]["vault_g"], data["closing"]["vault_g"]) == ("0.000", "2500.000")
    assert_adds_up(data)


def test_every_seeded_day_adds_up(client):
    sign_in(client, "finance")
    for day in [
        "2026-06-30", "2026-07-01", "2026-07-06", "2026-09-02", "2026-10-15",
        "2026-10-24", "2026-10-25", "2026-10-27", "2026-10-28", "2026-10-31",
        "2026-11-01", "2026-11-02", NEW_DAY,
    ]:
        assert_adds_up(view(client, day))


def test_a_quiet_day_has_no_movements_and_still_adds_up(client):
    sign_in(client, "finance")
    data = view(client, NEW_DAY)
    assert all(m["count"] == 0 and m["effect_g"] == "0.000" for m in data["movements"])
    assert data["opening"]["vault_g"] == data["closing"]["vault_g"] == "2252.514"
    assert data["closed"] is None


def test_todays_activity_reconciles(client):
    today = today_ist().isoformat()
    sign_in(client, "clerk")
    assert client.post("/api/issues", json=issue_body(client)).status_code == 201
    receipt = client.post("/api/receipts", json=receipt_body(gross_weight="10.000"))
    assert receipt.status_code == 201
    assert client.post("/api/old-gold", json=og_body()).status_code == 201
    switch(client, "finance")
    reversal = client.post(
        f"/api/entries/{receipt.json()['txn_no']}/reverse", json={"reason": "Wrong weight entered"}
    )
    assert reversal.status_code == 201
    assert client.post("/api/old-gold/OG-5003/void", json={"reason": "Recorded twice"}).status_code == 200
    data = view(client, today)
    found = lines(data)
    assert (found["issued"]["count"], found["issued"]["effect_g"]) == (1, "-109.920")
    assert (found["returned"]["count"], found["returned"]["effect_g"]) == (1, "+9.160")
    assert (found["corrections"]["count"], found["corrections"]["effect_g"]) == (1, "-9.160")
    assert (found["old_gold"]["count"], found["old_gold"]["effect_g"]) == (1, "+9.160")
    assert (found["old_gold_void"]["count"], found["old_gold_void"]["effect_g"]) == (1, "-46.487")
    assert_adds_up(data)


def test_future_dates_are_refused(client):
    sign_in(client, "finance")
    assert client.get("/api/closing/day", params={"date": "2099-01-01"}).status_code == 422
    assert client.get("/api/closing/day", params={"date": "nope"}).status_code == 422


# --- seeded closes ---------------------------------------------------------------------------

def test_the_seeded_closes_match_the_live_figures(client):
    sign_in(client, "finance")
    matching = view(client, "2026-11-01")["closed"]
    assert matching["counted_vault_g"] == "2206.027"
    assert matching["difference_g"] == "0.000"
    assert matching["note"] is None
    assert matching["by"] == "Demo Finance Head"
    assert matching["changed_since_close"] is False
    short = view(client, "2026-11-02")["closed"]
    assert short["expected_vault_g"] == "2252.514"
    assert short["counted_vault_g"] == "2252.509"
    assert short["difference_g"] == "-0.005"
    assert short["note"].startswith("Small weighing difference")
    assert short["changed_since_close"] is False


def test_history_is_newest_first(client):
    sign_in(client, "finance")
    rows = client.get("/api/closing/history").json()
    assert [r["close_date"] for r in rows] == ["2026-11-02", "2026-11-01"]
    assert rows[0]["difference_g"] == "-0.005"
    assert client.get("/api/closing/history", params={"limit": 0}).status_code == 422


# --- closing a day -------------------------------------------------------------------------------

def test_closing_a_day_that_matches(client, engine):
    sign_in(client, "finance")
    response = close(client, NEW_DAY, "2252.514")
    assert response.status_code == 201
    closed = response.json()["closed"]
    assert closed["difference_g"] == "0.000"
    assert closed["note"] is None
    assert closed["changed_since_close"] is False
    assert view(client, NEW_DAY)["closed"]["counted_vault_g"] == "2252.514"
    with Session(engine) as session:
        details = list(session.scalars(select(AuditLog.detail).where(AuditLog.action == "day.closed")))
    assert any(NEW_DAY in d and "difference 0.000" in d for d in details)


def test_a_day_can_only_be_closed_once(client):
    sign_in(client, "finance")
    assert close(client, NEW_DAY, "2252.514").status_code == 201
    assert close(client, NEW_DAY, "2252.514").status_code == 409
    assert close(client, "2026-11-02", "2252.514").status_code == 409


def test_a_difference_needs_a_note(client):
    sign_in(client, "finance")
    refused = close(client, NEW_DAY, "2252.000")
    assert refused.status_code == 422
    assert "note" in refused.json()["detail"]
    assert close(client, NEW_DAY, "2252.000", note="no").status_code == 422
    ok = close(client, NEW_DAY, "2252.000", note="  Counted   twice, dust in the tray ")
    assert ok.status_code == 201
    assert ok.json()["closed"]["difference_g"] == "-0.514"
    assert ok.json()["closed"]["note"] == "Counted twice, dust in the tray"


def test_counting_more_than_expected_is_recorded_too(client):
    sign_in(client, "finance")
    ok = close(client, NEW_DAY, "2252.600", note="Found a bag in the safe")
    assert ok.status_code == 201
    assert ok.json()["closed"]["difference_g"] == "+0.086"


@pytest.mark.parametrize("bad", ["abc", "", "-1", "1.2345", "1e3"])
def test_bad_counted_weights_are_rejected(client, bad):
    sign_in(client, "finance")
    assert close(client, NEW_DAY, bad).status_code == 422


def test_json_numbers_and_unknown_fields_are_rejected(client):
    sign_in(client, "finance")
    assert close(client, NEW_DAY, 2252.514).status_code == 422
    assert close(client, NEW_DAY, "2252.514", force=True).status_code == 422
    assert client.post("/api/closing/close", json={"counted_vault": "1.000"}).status_code == 422


def test_a_future_day_cannot_be_closed(client):
    sign_in(client, "finance")
    assert close(client, "2099-01-01", "1.000").status_code == 422


def test_a_day_that_does_not_add_up_cannot_be_closed(client, monkeypatch):
    sign_in(client, "finance")
    monkeypatch.setattr("app.routers.closing.reconciles", lambda *args: False)
    response = close(client, NEW_DAY, "2252.514")
    assert response.status_code == 409
    assert "add up" in response.json()["detail"]


def test_figures_changing_after_a_close_are_flagged(client):
    today = today_ist().isoformat()
    sign_in(client, "finance")
    expected = view(client, today)["closing"]["vault_g"]
    assert close(client, today, expected).status_code == 201
    switch(client, "clerk")
    assert client.post("/api/issues", json=issue_body(client)).status_code == 201
    switch(client, "finance")
    after = view(client, today)
    assert after["closed"]["changed_since_close"] is True
    assert after["closed"]["expected_vault_g"] == expected
    assert after["closing"]["vault_g"] != expected


def test_closes_cannot_be_edited_or_deleted(engine):
    with Session(engine) as session:
        with pytest.raises(DBAPIError):
            session.execute(text("UPDATE day_closes SET note = 'x'"))
        session.rollback()
        with pytest.raises(DBAPIError):
            session.execute(text("DELETE FROM day_closes"))