from dataclasses import dataclass
from typing import Protocol

WEIGHT = "WEIGHT"
PURITY = "PURITY"


class ReaderUnavailable(Exception):
    """A reader couldn't do its job. The message is safe to show to the clerk."""


@dataclass(frozen=True)
class ReaderResult:
    value: str | None  # already validated and formatted, or None if unreadable


class Reader(Protocol):
    name: str

    def available(self) -> bool: ...

    def read(self, target: str, jpeg: bytes) -> ReaderResult: ...