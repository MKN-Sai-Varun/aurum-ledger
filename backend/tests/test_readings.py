import hashlib
import io

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import AuditLog, Reading
from app.routers.readings import get_providers, usage_limiter
from tests.test_karigars import sign_in
from tests.test_readers import Fake


@pytest.fixture(autouse=True)
def fresh_usage_counter():
    usage_limiter.clear()
    yield
    usage_limiter.clear()


def photo():
    buffer = io.BytesIO()
    Image.new("RGB", (120, 60), (200, 210, 190)).save(buffer, "PNG")
    return buffer.getvalue()


def upload(client, target="WEIGHT", data=None, name="scale.png"):
    content = photo() if data is None else data
    return client.post(
        "/api/readings",
        data={"target": target},
        files={"image": (name, content, "image/png")},
    )


def use(*providers):
    app.dependency_overrides[get_providers] = lambda: list(providers)


def test_readings_are_for_the_clerk_only(client):
    use(Fake("GEMINI", "1.000"))
    assert upload(client).status_code == 401
    sign_in(client, "finance")
    assert upload(client).status_code == 403


def test_a_successful_reading_is_returned_and_recorded(client, engine):
    use(Fake("GEMINI", "112.450"))
    sign_in(client, "clerk")
    data = photo()
    response = upload(client, data=data)
    assert response.status_code == 201
    body = response.json()
    assert body["value"] == "112.450"
    assert body["readable"] is True
    assert body["source"] == "GEMINI"
    assert body["source_label"] == "AI reader"
    assert body["notes"] == []
    with Session(engine) as session:
        row = session.get(Reading, body["id"])
        actions = list(session.scalars(select(AuditLog.action)))
    assert row.target == "WEIGHT"
    assert row.source == "GEMINI"
    assert row.value_text == "112.450"
    assert row.status == "PENDING"
    assert row.confirmed_text is None
    assert row.image_sha256 == hashlib.sha256(data).hexdigest()
    assert "reading.created" in actions


def test_the_second_reader_takes_over_when_the_first_fails(client):
    use(
        Fake("GEMINI", fail="The Gemini reader is busy right now (free quota)."),
        Fake("TESSERACT", "91.60"),
    )
    sign_in(client, "clerk")
    body = upload(client, target="PURITY").json()
    assert body["source"] == "TESSERACT"
    assert body["source_label"] == "Local reader"
    assert body["value"] == "91.60"
    assert body["notes"] == ["The Gemini reader is busy right now (free quota)."]


def test_an_unreadable_photo_is_still_a_normal_answer(client, engine):
    use(Fake("GEMINI"), Fake("TESSERACT"))
    sign_in(client, "clerk")
    response = upload(client)
    assert response.status_code == 201
    body = response.json()
    assert body["value"] is None
    assert body["readable"] is False
    assert body["source"] == "NONE"
    assert body["notes"][-1] == "Type the value from the display."
    with Session(engine) as session:
        assert session.get(Reading, body["id"]).value_text is None


def test_no_readers_configured_still_works_manually(client):
    use(
        Fake("GEMINI", "1.000", available=False),
        Fake("TESSERACT", "1.000", available=False),
    )
    sign_in(client, "clerk")
    body = upload(client).json()
    assert body["readable"] is False
    assert body["notes"] == [
        "The Gemini reader isn't set up.",
        "The local reader isn't set up.",
        "Type the value from the display.",
    ]


def test_bad_targets_and_missing_files_are_rejected(client):
    use(Fake("GEMINI", "1.000"))
    sign_in(client, "clerk")
    assert upload(client, target="COLOUR").status_code == 422
    assert client.post("/api/readings", data={"target": "WEIGHT"}).status_code == 422


@pytest.mark.parametrize(
    "data, text",
    [(b"", "empty"), (b"not a photo", "readable photo"), (b"x" * (5 * 1024 * 1024 + 1), "5 MB")],
)
def test_bad_uploads_are_rejected_with_a_clear_message(client, data, text):
    use(Fake("GEMINI", "1.000"))
    sign_in(client, "clerk")
    response = upload(client, data=data)
    assert response.status_code == 422
    assert text in response.json()["detail"]


def test_rejected_uploads_are_not_recorded(client, engine):
    use(Fake("GEMINI", "1.000"))
    sign_in(client, "clerk")
    upload(client, data=b"not a photo")
    with Session(engine) as session:
        assert session.scalar(select(Reading.id)) is None


def test_too_many_readings_are_slowed_down(client):
    use(Fake("GEMINI", "1.000"))
    sign_in(client, "clerk")
    for _ in range(30):
        assert upload(client).status_code == 201
    response = upload(client)
    assert response.status_code == 429
    assert "Too many" in response.json()["detail"]