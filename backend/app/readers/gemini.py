import base64
import json
import re

import httpx

from app.readers.base import PURITY, WEIGHT, ReaderResult, ReaderUnavailable
from app.readers.values import clean_value

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_RE = re.compile(r"[A-Za-z0-9._-]{1,60}")

PROMPTS = {
    WEIGHT: (
        "This is a photo of a digital weighing scale display. Read the weight number "
        "shown on the display. Return it in grams exactly as shown, with every digit "
        "including the decimal point, for example 112.450. If the display shows a unit "
        "other than grams, if more than one number could be the weight, or if the "
        "digits are not clearly legible, set readable to false and value to null. "
        "Never estimate or guess a digit."
    ),
    PURITY: (
        "This is a photo or printout from a gold karat (purity) meter. Find the gold "
        "purity percentage, often labelled Au, Gold or Fineness, for example 91.60. "
        "Return only that percentage number. If only karats are shown, if several "
        "different results are shown, or if the digits are not clearly legible, set "
        "readable to false and value to null. Never estimate or guess a digit."
    ),
}

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "readable": {"type": "BOOLEAN"},
        "value": {"type": "STRING", "nullable": True},
    },
    "required": ["readable"],
}


class GeminiReader:
    name = "GEMINI"

    def __init__(self, api_key: str, model: str, transport=None, timeout: float = 20.0):
        self._api_key = api_key
        self._model = model
        self._transport = transport
        self._timeout = timeout

    def available(self) -> bool:
        return bool(self._api_key) and bool(_MODEL_RE.fullmatch(self._model))

    def read(self, target: str, jpeg: bytes) -> ReaderResult:
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPTS[target]},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(jpeg).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        url = f"{BASE_URL}/{self._model}:generateContent"
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(
                    url, headers={"x-goog-api-key": self._api_key}, json=body
                )
        except httpx.HTTPError as exc:
            raise ReaderUnavailable("The Gemini reader couldn't be reached.") from exc

        if response.status_code == 503:
            raise ReaderUnavailable("The Gemini reader is busy right now (high demand).")
        if response.status_code == 429:
            raise ReaderUnavailable("The Gemini reader is busy right now (free quota).")
        if response.status_code in (400, 401, 403, 404):
            raise ReaderUnavailable("The Gemini reader isn't set up correctly.")
        if response.status_code != 200:
            raise ReaderUnavailable("The Gemini reader had a problem.")

        try:
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ReaderUnavailable("The Gemini reader gave an unexpected answer.") from exc

        if not isinstance(data, dict) or data.get("readable") is not True:
            return ReaderResult(None)
        return ReaderResult(clean_value(target, data.get("value")))