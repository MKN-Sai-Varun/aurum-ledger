from dataclasses import dataclass, field

from app.readers.base import ReaderUnavailable

LABELS = {
    "GEMINI": "The Gemini reader",
    "TESSERACT": "The local reader",
}


@dataclass
class ReadOutcome:
    source: str
    value: str | None
    notes: list[str] = field(default_factory=list)


def read_value(providers, target: str, jpeg: bytes) -> ReadOutcome:
    """Try each reader in order and stop at the first that gives a valid value.

    A reader that isn't set up is only mentioned when nothing could read the photo.
    """
    notes: list[str] = []
    skipped: list[str] = []
    for provider in providers:
        label = LABELS.get(provider.name, provider.name)
        if not provider.available():
            skipped.append(f"{label} isn't set up.")
            continue
        try:
            result = provider.read(target, jpeg)
        except ReaderUnavailable as exc:
            notes.append(str(exc))
            continue
        if result.value is not None:
            return ReadOutcome(provider.name, result.value, notes)
        notes.append(f"{label} couldn't read the value clearly.")
    return ReadOutcome("NONE", None, skipped + notes + ["Type the value from the display."])