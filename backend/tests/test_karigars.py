import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, LedgerEntry
from tests.conftest import CLERK_PW, FINANCE_PW


def sign_in(client, who):
    password = CLERK_PW if who == "clerk" else FINANCE_PW
    response = client.post("/api/auth/login", json={"username": who, "password": password})
    assert response.status_code == 200


def by_name(client, name):
    rows = client.get("/api/karigars").json()
    return next(row for row in rows if row["name"] == name)


def category_id(client, name):
    rows = client.get("/api/categories").json()
    return next(row["id"] for row in rows if row["name"] == name)


def test_list_requires_sign_in(client):
    assert client.get("/api/karigars").status_code == 401
    assert client.get("/api/categories").status_code == 401


def test_clerk_can_list_karigars_with_rates(client):
    sign_in(client, "clerk")
    rows = client.get("/api/karigars").json()
    assert len(rows) == 6
    murugesan = by_name(client, "Murugesan S")
    rates = {w["category"]: w["wastage_pct"] for w in murugesan["wastage"]}
    assert rates["Necklace"] == "3.00"
    assert rates["Chain"] == "2.50"


def test_list_shows_open_job_count(client):
    sign_in(client, "clerk")
    assert by_name(client, "Ramesh P")["open_jobs"] == 1
    assert by_name(client, "Murugesan S")["open_jobs"] == 0


def test_categories_listed(client):
    sign_in(client, "clerk")
    names = [c["name"] for c in client.get("/api/categories").json()]
    assert names == ["Bangle", "Chain", "Earring", "Necklace", "Ring"]


def test_clerk_cannot_create_karigar(client):
    sign_in(client, "clerk")
    assert client.post("/api/karigars", json={"name": "New Person"}).status_code == 403


def test_finance_creates_karigar(client):
    sign_in(client, "finance")
    response = client.post("/api/karigars", json={"name": "  Gopal   T  "})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Gopal T"
    assert body["is_active"] is True
    assert body["wastage"] == []
    assert by_name(client, "Gopal T")["id"] == body["id"]


def test_duplicate_name_rejected_case_insensitively(client):
    sign_in(client, "finance")
    assert client.post("/api/karigars", json={"name": "selvam k"}).status_code == 409


def test_blank_name_rejected(client):
    sign_in(client, "finance")
    assert client.post("/api/karigars", json={"name": "   "}).status_code == 422


def test_finance_sets_a_rate_and_it_is_audited(client, engine):
    sign_in(client, "finance")
    karigar = by_name(client, "Murugesan S")
    response = client.put(
        f"/api/karigars/{karigar['id']}/wastage/{category_id(client, 'Necklace')}",
        json={"wastage_pct": "3.75"},
    )
    assert response.status_code == 200
    rates = {w["category"]: w["wastage_pct"] for w in response.json()["wastage"]}
    assert rates["Necklace"] == "3.75"
    with Session(engine) as session:
        details = list(
            session.scalars(select(AuditLog.detail).where(AuditLog.action == "karigar.rate_set"))
        )
    assert any("3.00 -> 3.75" in detail for detail in details)


@pytest.mark.parametrize("bad", ["100.01", "abc", "3.005"])
def test_invalid_rates_rejected(client, bad):
    sign_in(client, "finance")
    karigar = by_name(client, "Murugesan S")
    response = client.put(
        f"/api/karigars/{karigar['id']}/wastage/{category_id(client, 'Necklace')}",
        json={"wastage_pct": bad},
    )
    assert response.status_code == 422


def test_clerk_cannot_set_a_rate(client):
    sign_in(client, "clerk")
    karigar = by_name(client, "Murugesan S")
    response = client.put(
        f"/api/karigars/{karigar['id']}/wastage/{category_id(client, 'Necklace')}",
        json={"wastage_pct": "1.00"},
    )
    assert response.status_code == 403


def test_unknown_karigar_and_category_return_404(client):
    sign_in(client, "finance")
    assert client.get("/api/karigars/9999").status_code == 404
    karigar = by_name(client, "Murugesan S")
    response = client.put(
        f"/api/karigars/{karigar['id']}/wastage/9999",
        json={"wastage_pct": "3.00"},
    )
    assert response.status_code == 404


def test_cannot_deactivate_karigar_with_open_jobs(client):
    sign_in(client, "finance")
    karigar = by_name(client, "Ramesh P")
    response = client.patch(f"/api/karigars/{karigar['id']}", json={"is_active": False})
    assert response.status_code == 409
    assert by_name(client, "Ramesh P")["is_active"] is True


def test_can_deactivate_karigar_without_open_jobs(client):
    sign_in(client, "finance")
    karigar = by_name(client, "Murugesan S")
    response = client.patch(f"/api/karigars/{karigar['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_rate_change_does_not_rewrite_ledger_history(client, engine):
    sign_in(client, "finance")
    karigar = by_name(client, "Murugesan S")
    client.put(
        f"/api/karigars/{karigar['id']}/wastage/{category_id(client, 'Necklace')}",
        json={"wastage_pct": "5.00"},
    )
    with Session(engine) as session:
        entry = session.scalar(select(LedgerEntry).where(LedgerEntry.txn_no == "TX-30411"))
    assert entry.wastage_hundredths == 300


def test_patch_needs_at_least_one_field(client):
    sign_in(client, "finance")
    karigar = by_name(client, "Murugesan S")
    assert client.patch(f"/api/karigars/{karigar['id']}", json={}).status_code == 422


def test_extra_fields_rejected(client):
    sign_in(client, "finance")
    response = client.post("/api/karigars", json={"name": "Extra Fields", "role": "x"})
    assert response.status_code == 422