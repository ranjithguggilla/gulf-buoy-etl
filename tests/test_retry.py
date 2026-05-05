"""Tests for the exponential-backoff retry decorator."""

import pytest

from gbe.retry import retry


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


class TestRetry:
    def test_first_attempt_success(self):
        calls = {"n": 0}

        @retry(exceptions=(TransientError,), max_attempts=3, base_delay=0.0)
        def fn():
            calls["n"] += 1
            return 42

        assert fn() == 42
        assert calls["n"] == 1

    def test_retries_until_success(self):
        calls = {"n": 0}

        @retry(exceptions=(TransientError,), max_attempts=4, base_delay=0.0, jitter=False)
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TransientError("nope")
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 3

    def test_gives_up_after_max_attempts(self):
        calls = {"n": 0}

        @retry(exceptions=(TransientError,), max_attempts=3, base_delay=0.0, jitter=False)
        def fn():
            calls["n"] += 1
            raise TransientError("nope")

        with pytest.raises(TransientError):
            fn()
        assert calls["n"] == 3

    def test_permanent_error_not_retried(self):
        calls = {"n": 0}

        @retry(exceptions=(TransientError,), max_attempts=3, base_delay=0.0)
        def fn():
            calls["n"] += 1
            raise PermanentError("nope")

        with pytest.raises(PermanentError):
            fn()
        assert calls["n"] == 1
