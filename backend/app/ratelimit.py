"""Small in-memory login lockout. It resets when the server restarts."""
import time
from collections import deque


class LoginLimiter:
    def __init__(self, max_failures=5, window_seconds=900, max_keys=10_000, clock=time.monotonic):
        self._max = max_failures
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._failures: dict[str, deque] = {}

    def _prune(self, key: str) -> deque:
        entries = self._failures.get(key)
        if entries is None:
            return deque()
        cutoff = self._clock() - self._window
        while entries and entries[0] <= cutoff:
            entries.popleft()
        if not entries:
            del self._failures[key]
            return deque()
        return entries

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self._max

    def record_failure(self, key: str) -> None:
        if len(self._failures) >= self._max_keys:
            self._failures.clear()
        entries = self._prune(key)
        entries.append(self._clock())
        self._failures[key] = entries

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def clear(self) -> None:
        self._failures.clear()