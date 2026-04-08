"""
Exponential-backoff retry decorator for transient network errors.

Used by every source adapter (ndbc.py, tabs.py) and the Zenodo publisher.
Non-recoverable errors (HTTP 4xx other than 429) raise immediately.
"""

from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import Callable, Iterable, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    exceptions: Iterable[Type[BaseException]] = (Exception,),
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator: retry a function with exponential backoff.

    Args:
        exceptions: Tuple of exception types that trigger a retry.
        max_attempts: Total attempts including the first call.
        base_delay: Initial sleep between attempts (seconds).
        max_delay: Cap on a single sleep interval.
        jitter: Add random +/- 25% jitter to avoid thundering herd.

    Returns:
        Decorator that wraps the target function.
    """
    exc_tuple = tuple(exceptions)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except exc_tuple as exc:
                    if attempt >= max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, attempt, exc,
                        )
                        raise

                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    if jitter:
                        delay = delay * (1.0 + random.uniform(-0.25, 0.25))

                    logger.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.2fs",
                        func.__name__, attempt, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
        return wrapper

    return decorator
