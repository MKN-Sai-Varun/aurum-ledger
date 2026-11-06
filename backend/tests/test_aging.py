from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.aging import age_days, bucket_key
from app.models import AuditLog
from tests.test_corrections import switch
from tests.test_jobs import receipt_body
from tests.test_karigars import sign_in

DAY = date(2026, 11, 6)


def freeze(monkeypatch, day=DAY):
    monkeypatch.setattr("app.routers.aging.today_ist", lambda: day)


def board(client):
    response = client.get("/api/job-aging")
    assert response.status_code == 200
    return response.json()


def by_job(data):
    return {job["job_no"]: job for b in data["buckets"] for job in b["jobs"]}


def counts(data):
    return [b["count"] for b in data["buckets"]]


# --- the band maths --------------------------------------------------------------------

@pytest.mark.parametrize(
    "age, key",
    [(0, "0-2"), (2, "0-2"), (3, "3-7"), (7, "3-7"), (8, "8-14"), (14, "8-14"), (15, "15+"), (400, "15+")],
)
def test_band_boundaries(age, key):
    assert bucket_key(age) == key


def test_band_rejects_bad_ages():
    with pytest.raises(ValueError):
        bucket_key(-1)
    with pytest.raises(TypeError):
        bucket_key(2.5)


def test_age_counts_whole_days_and_is_never_negative():
    assert age_days(date(2026, 10, 30), date(2026, 11, 6)) == 7
    assert age_days(date(2026, 11, 6), date(2026, 11, 6)) == 0
    assert age_days(date(2026, 11, 9), date(2026, 11, 6)) == 0


# --- the board -------------------------------------------------------------------------

def test_the_board_is_finance_only(client):
    assert client.get("/api/job-aging").status_code == 401
    sign_in(client, "clerk")
    assert client.get("/api/job-aging").status_code == 403


def test_the_seeded_board(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "finance")
    data = board(client)
    assert data["as_of"] == "2026-11-06"
    assert data["total_open"] == 4
    assert data["total_outstanding_g"] == "187.780"
    assert [b["key"] for b in data["buckets"]] == ["0-2", "3-7", "8-14", "15+"]
    assert counts(data) == [0, 3, 1, 0]
    assert [b["outstanding_g"] for b in data["buckets"]] == ["0.000", "109.920", "77.860", "0.000"]


def test_jobs_are_oldest_first_within_a_band(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "finance")
    middle = board(client)["buckets"][1]["jobs"]
    assert [j["job_no"] for j in middle] == ["JOB-1044", "JOB-1046", "JOB-1045"]


def test_a_card_carries_the_figures_and_dates(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "finance")
    job = by_job(board(client))["JOB-1046"]
    assert job["karigar"] == "Dhanapal V"
    assert job["category"] == "Earring"
    assert job["opened_on"] == "2026-10-30"
    assert job["age_days"] == 7
    assert job["issued_fine_g"] == "22.900"
    assert job["outstanding_g"] == "13.740"
    assert job["last_activity"] == "2026-11-01"
    assert job["days_since_activity"] == 5
    assert job["followups"] == 0
    assert job["last_followup_note"] is None


def test_the_seeded_follow_up_shows(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "finance")
    job = by_job(board(client))["JOB-1043"]
    assert job["age_days"] == 8
    assert job["followups"] == 1
    assert job["last_followup_on"] == "2026-11-04"
    assert job["last_followup_note"].startswith("Asked for an update")
    assert job["last_followup_by"] == "Demo Finance Head"


def test_jobs_move_to_older_bands_as_time_passes(client, monkeypatch):
    freeze(monkeypatch, date(2026, 11, 20))
    sign_in(client, "finance")
    assert counts(board(client)) == [0, 0, 0, 4]


def test_closed_jobs_leave_the_board(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "clerk")
    assert client.post("/api/jobs/JOB-1044/close").status_code == 200
    switch(client, "finance")
    data = board(client)
    assert data["total_open"] == 3
    assert "JOB-1044" not in by_job(data)
    assert counts(data) == [0, 2, 1, 0]


def test_a_receipt_lowers_the_outstanding_gold(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "clerk")
    assert client.post("/api/receipts", json=receipt_body()).status_code == 201
    switch(client, "finance")
    data = board(client)
    assert by_job(data)["JOB-1044"]["outstanding_g"] == "4.580"
    assert data["buckets"][1]["outstanding_g"] == "45.800"


# --- follow-ups -------------------------------------------------------------------------

def follow_up(client, job_no="JOB-1044", note="Called the karigar, due back on Monday"):
    return client.post(f"/api/job-aging/{job_no}/follow-ups", json={"note": note})


def test_follow_ups_are_for_the_finance_head(client):
    assert follow_up(client).status_code == 401
    sign_in(client, "clerk")
    assert follow_up(client).status_code == 403


def test_a_follow_up_is_recorded_and_shown(client, monkeypatch, engine):
    freeze(monkeypatch)
    sign_in(client, "finance")
    response = follow_up(client, note="  Called   the karigar ")
    assert response.status_code == 201
    body = response.json()
    assert body["job_no"] == "JOB-1044"
    assert body["followed_up_on"] == "2026-11-06"
    assert body["note"] == "Called the karigar"
    assert body["by"] == "Demo Finance Head"
    job = by_job(board(client))["JOB-1044"]
    assert job["followups"] == 1
    assert job["last_followup_note"] == "Called the karigar"
    with Session(engine) as session:
        actions = list(session.scalars(select(AuditLog.action)))
    assert "job.followed_up" in actions


def test_the_latest_follow_up_wins(client, monkeypatch):
    freeze(monkeypatch)
    sign_in(client, "finance")
    follow_up(client, "JOB-1043", "First reminder sent")
    follow_up(client, "JOB-1043", "Second reminder sent")
    job = by_job(board(client))["JOB-1043"]
    assert job["followups"] == 3
    assert job["last_followup_note"] == "Second reminder sent"


def test_the_job_number_is_case_insensitive(client):
    sign_in(client, "finance")
    assert follow_up(client, "job-1044").status_code == 201


def test_unknown_and_closed_jobs_are_refused(client):
    sign_in(client, "finance")
    assert follow_up(client, "JOB-9999").status_code == 404
    assert follow_up(client, "JOB-1041").status_code == 409


@pytest.mark.parametrize("bad", ["", "ab", "   ", "x" * 201])
def test_bad_notes_are_rejected(client, bad):
    sign_in(client, "finance")
    assert follow_up(client, note=bad).status_code == 422


def test_unknown_fields_are_rejected(client):
    sign_in(client, "finance")
    response = client.post(
        "/api/job-aging/JOB-1044/follow-ups", json={"note": "Called him", "send": True}
    )
    assert response.status_code == 422