from app.ratelimit import LoginLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_blocks_after_max_failures():
    limiter = LoginLimiter(max_failures=3, window_seconds=60, clock=Clock())
    for _ in range(3):
        assert not limiter.is_blocked("a")
        limiter.record_failure("a")
    assert limiter.is_blocked("a")


def test_block_expires_after_the_window():
    clock = Clock()
    limiter = LoginLimiter(max_failures=2, window_seconds=60, clock=clock)
    limiter.record_failure("a")
    limiter.record_failure("a")
    assert limiter.is_blocked("a")
    clock.now = 61.0
    assert not limiter.is_blocked("a")


def test_reset_clears_failures():
    limiter = LoginLimiter(max_failures=2, window_seconds=60, clock=Clock())
    limiter.record_failure("a")
    limiter.record_failure("a")
    limiter.reset("a")
    assert not limiter.is_blocked("a")


def test_keys_are_independent():
    limiter = LoginLimiter(max_failures=1, window_seconds=60, clock=Clock())
    limiter.record_failure("a")
    assert limiter.is_blocked("a")
    assert not limiter.is_blocked("b")