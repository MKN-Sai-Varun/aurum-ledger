import base64
import io
import json

import httpx
import pytest
from PIL import Image

from app.readers import image as image_module
from app.readers.base import PURITY, WEIGHT, ReaderResult, ReaderUnavailable
from app.readers.gemini import GeminiReader
from app.readers.image import MAX_BYTES, prepare_image
from app.readers.service import read_value
from app.readers.values import clean_value, find_candidates


def png(size=(120, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 210, 190)).save(buffer, "PNG")
    return buffer.getvalue()


# --- values -------------------------------------------------------------------

@pytest.mark.parametrize(
    "target, raw, expected",
    [
        (WEIGHT, "112.450", "112.450"),
        (WEIGHT, "112.45", "112.450"),
        (WEIGHT, " 3.3 ", "3.300"),
        (WEIGHT, "112.450 g", "112.450"),
        (WEIGHT, "112.450 Grams", "112.450"),
        (PURITY, "91.6", "91.60"),
        (PURITY, "91.60 %", "91.60"),
        (PURITY, "99.99", "99.99"),
    ],
)
def test_clean_value_accepts_and_formats(target, raw, expected):
    assert clean_value(target, raw) == expected


@pytest.mark.parametrize(
    "target, raw",
    [
        (WEIGHT, "0"), (WEIGHT, "0.000"), (WEIGHT, "2000.001"), (WEIGHT, "-5"),
        (WEIGHT, "abc"), (WEIGHT, ""), (WEIGHT, "1.2345"), (WEIGHT, None), (WEIGHT, 112.45),
        (PURITY, "0"), (PURITY, "100.5"), (PURITY, "91.605"), (PURITY, "22K"),
        ("OTHER", "1.00"),
    ],
)
def test_clean_value_rejects_impossible_readings(target, raw):
    assert clean_value(target, raw) is None


def test_find_candidates_picks_plausible_numbers_once():
    assert find_candidates(WEIGHT, "ref 12345.6789  112.450\n112.450  x") == ["112.450"]
    assert find_candidates(WEIGHT, "nothing here") == []
    assert find_candidates(WEIGHT, "") == []
    assert find_candidates(PURITY, "Au 91.60 % 22K") == ["91.60"]
    # 112.45 is above 100, so it can't be a purity and is dropped.
    assert find_candidates(PURITY, "112.45 91.6") == ["91.60"]


def test_find_candidates_needs_a_decimal_point():
    assert find_candidates(WEIGHT, "112450") == []
    assert find_candidates(PURITY, "22") == []


# --- photo checks ----------------------------------------------------------------

def test_prepare_image_returns_a_clean_jpeg():
    out = prepare_image(png())
    assert Image.open(io.BytesIO(out)).format == "JPEG"


def test_prepare_image_shrinks_large_photos():
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 2000), (10, 20, 30)).save(buffer, "PNG")
    out = Image.open(io.BytesIO(prepare_image(buffer.getvalue())))
    assert max(out.size) <= 1600


def test_prepare_image_strips_metadata():
    exif = Image.Exif()
    exif[0x010F] = "SomeCameraMaker"
    buffer = io.BytesIO()
    Image.new("RGB", (80, 60)).save(buffer, "JPEG", exif=exif)
    assert len(Image.open(io.BytesIO(buffer.getvalue())).getexif()) > 0
    cleaned = Image.open(io.BytesIO(prepare_image(buffer.getvalue())))
    assert len(cleaned.getexif()) == 0


def test_prepare_image_rejects_bad_input():
    with pytest.raises(ValueError, match="empty"):
        prepare_image(b"")
    with pytest.raises(ValueError, match="5 MB"):
        prepare_image(b"x" * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="readable photo"):
        prepare_image(b"this is not a photo")
    gif = io.BytesIO()
    Image.new("P", (10, 10)).save(gif, "GIF")
    with pytest.raises(ValueError, match="JPEG, PNG or WebP"):
        prepare_image(gif.getvalue())


def test_prepare_image_rejects_huge_dimensions(monkeypatch):
    monkeypatch.setattr(image_module, "MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="too large"):
        prepare_image(png((20, 20)))


# --- the Gemini reader, with the network replaced ----------------------------------

GEMINI_MODEL = "gemini-2.5-flash"


def gemini_reply(obj):
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}
    )


def gemini(handler, key="test-key", model=GEMINI_MODEL):
    return GeminiReader(key, model, transport=httpx.MockTransport(handler))


def test_gemini_reads_and_formats_a_value():
    captured = {}

    def handler(request):
        captured["request"] = request
        return gemini_reply({"readable": True, "value": "112.45"})

    assert gemini(handler).read(WEIGHT, b"jpeg-bytes").value == "112.450"
    request = captured["request"]
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(request.url)
    assert "gemini-2.5-flash:generateContent" in str(request.url)
    body = json.loads(request.content)
    part = body["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "image/jpeg"
    assert base64.b64decode(part["data"]) == b"jpeg-bytes"
    assert body["generationConfig"]["temperature"] == 0
    assert "test-key" not in request.content.decode()


def test_gemini_says_nothing_when_unreadable():
    for obj in (
        {"readable": False, "value": None},
        {"readable": True, "value": None},
        {"readable": False, "value": "112.450"},
    ):
        assert gemini(lambda r, o=obj: gemini_reply(o)).read(WEIGHT, b"x").value is None


@pytest.mark.parametrize(
    "target, value", [(WEIGHT, "2500.000"), (WEIGHT, "abc"), (PURITY, "100.5"), (PURITY, "22K")]
)
def test_gemini_impossible_values_are_discarded(target, value):
    assert gemini(lambda r: gemini_reply({"readable": True, "value": value})).read(target, b"x").value is None


@pytest.mark.parametrize(
    "status, text",
    [(429, "busy"), (403, "isn't set up"), (404, "isn't set up"), (500, "problem")],
)
def test_gemini_http_errors_become_safe_messages(status, text):
    with pytest.raises(ReaderUnavailable, match=text):
        gemini(lambda r: httpx.Response(status, text="secret server detail")).read(WEIGHT, b"x")


def test_gemini_malformed_answers_are_reported():
    for response in (
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}),
    ):
        with pytest.raises(ReaderUnavailable, match="unexpected"):
            gemini(lambda r, resp=response: resp).read(WEIGHT, b"x")


def test_gemini_network_failure_hides_details():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(ReaderUnavailable) as caught:
        gemini(handler).read(WEIGHT, b"x")
    assert "boom" not in str(caught.value)


def test_gemini_availability():
    assert gemini(lambda r: gemini_reply({})).available() is True
    assert GeminiReader("", GEMINI_MODEL).available() is False
    assert GeminiReader("key", "bad model/../name").available() is False



# --- the fallback chain ------------------------------------------------------------

class Fake:
    def __init__(self, name, value=None, available=True, fail=None):
        self.name = name
        self._value = value
        self._available = available
        self._fail = fail
        self.calls = 0

    def available(self):
        return self._available

    def read(self, target, jpeg):
        self.calls += 1
        if self._fail:
            raise ReaderUnavailable(self._fail)
        return ReaderResult(self._value)


def test_first_reader_wins_and_the_second_is_not_called():
    first, second = Fake("GEMINI", "112.450"), Fake("TESSERACT", "999.000")
    outcome = read_value([first, second], WEIGHT, b"x")
    assert (outcome.source, outcome.value) == ("GEMINI", "112.450")
    assert second.calls == 0


def test_a_failing_reader_falls_back_and_says_so():
    outcome = read_value(
        [
            Fake("GEMINI", fail="The Gemini reader is busy right now (free quota)."),
            Fake("TESSERACT", "112.450"),
        ],
        WEIGHT,
        b"x",
    )
    assert (outcome.source, outcome.value) == ("TESSERACT", "112.450")
    assert outcome.notes == ["The Gemini reader is busy right now (free quota)."]


def test_an_unconfigured_reader_is_skipped_quietly_when_another_succeeds():
    gemini_fake = Fake("GEMINI", "1.000", available=False)
    outcome = read_value([gemini_fake, Fake("TESSERACT", "2.000")], WEIGHT, b"x")
    assert gemini_fake.calls == 0
    assert outcome.value == "2.000"
    assert outcome.notes == []


def test_nothing_readable_leaves_the_clerk_to_type_it():
    outcome = read_value([Fake("GEMINI"), Fake("TESSERACT")], WEIGHT, b"x")
    assert (outcome.source, outcome.value) == ("NONE", None)
    assert outcome.notes == [
        "The Gemini reader couldn't read the value clearly.",
        "The local reader couldn't read the value clearly.",
        "Type the value from the display.",
    ]