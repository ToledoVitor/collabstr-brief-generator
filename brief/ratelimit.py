"""Per-client-IP rate limiting backed by the Django cache.

Fixed 60s window. Uses cache.add + cache.incr so the counter is atomic on
backends that support it (Redis/Memcached). LocMem is process-local — fine for
a single instance; use a shared cache for multi-instance deployments.
"""

from __future__ import annotations

import os

from django.core.cache import cache

_WINDOW_SECONDS = 60


def _limit() -> int:
    try:
        return int(os.getenv("RATE_LIMIT_PER_MIN", "12"))
    except ValueError:
        return 12


def check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if the IP is over its cap."""
    import time

    window = int(time.time()) // _WINDOW_SECONDS
    key = f"rl:{client_ip}:{window}"

    # First hit in this window — seed the counter with the window TTL.
    if cache.add(key, 1, timeout=_WINDOW_SECONDS):
        return True
    try:
        count = cache.incr(key)
    except ValueError:
        # Key expired between add() and incr(); treat as a fresh window.
        cache.set(key, 1, timeout=_WINDOW_SECONDS)
        return True
    return count <= _limit()
