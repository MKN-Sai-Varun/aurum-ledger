from tests.test_karigars import sign_in

BANNED = [
    "theft", "stole", "stolen", "steal", "fraud", "blame", "cheat",
    "guilty", "missing", "suspect", "culprit",
]


def alerts(client):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    return response.json()


def figures(alert):
    return {f["label"]: f["value"] for f in alert["figures"]}


def test_alerts_are_finance_only(client):
    assert client.get("/api/alerts").status_code == 401
    sign_in(client, "clerk")
    assert client.get("/api/alerts").status_code == 403


def test_seeded_counts(client):
    sign_in(client, "finance")
    body = alerts(client)
    assert body["drift_count"] == 1
    assert body["review_count"] == 5
    assert len(body["alerts"]) == 6


def test_the_trend_alert_is_first_and_explains_itself(client):
    sign_in(client, "finance")
    first = alerts(client)["alerts"][0]
    assert first["kind"] == "KARIGAR_DRIFT"
    assert first["karigar"] == "Selvam K"
    assert first["job_no"] == "JOB-1038"
    assert first["title"] == "Trend to review"
    values = figures(first)
    assert values["Latest difference"] == "1.50 %"
    assert values["Earlier average"] == "0.07 %"
    assert values["Earlier jobs"] == "3"


def test_job_reviews_are_newest_first(client):
    sign_in(client, "finance")
    reviews = [a for a in alerts(client)["alerts"] if a["kind"] == "JOB_REVIEW"]
    assert [a["job_no"] for a in reviews] == [
        "JOB-1041", "JOB-1038", "JOB-1029", "JOB-1024", "JOB-1027",
    ]


def test_the_brief_sample_job_alert(client):
    sign_in(client, "finance")
    alert = next(a for a in alerts(client)["alerts"] if a["job_no"] == "JOB-1041" and a["kind"] == "JOB_REVIEW")
    assert alert["karigar"] == "Murugesan S"
    assert alert["title"] == "Job to review"
    assert figures(alert) == {
        "Outstanding": "3.893 g",
        "Allowed wastage": "3.298 g",
        "Beyond the allowance": "0.595 g",
    }
    assert "0.595 g" in alert["message"]


def test_jobs_within_allowance_and_open_jobs_are_not_listed(client):
    sign_in(client, "finance")
    listed = {a["job_no"] for a in alerts(client)["alerts"] if a["kind"] == "JOB_REVIEW"}
    assert "JOB-1019" not in listed
    assert "JOB-1003" not in listed
    assert "JOB-1044" not in listed


def test_wording_is_never_accusatory(client):
    sign_in(client, "finance")
    for alert in alerts(client)["alerts"]:
        text = (alert["title"] + " " + alert["message"]).lower()
        for word in BANNED:
            assert word not in text


def test_rules_are_exposed_for_transparency(client):
    sign_in(client, "finance")
    rules = alerts(client)["rules"]
    assert len(rules) == 3
    assert "0.50" in rules[1]