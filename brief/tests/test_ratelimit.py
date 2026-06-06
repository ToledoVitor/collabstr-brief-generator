"""Unit tests for the cache-backed per-IP rate limiter."""

import os

from django.core.cache import cache
from django.test import SimpleTestCase

from brief.ratelimit import check_rate_limit


class RateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self._prev = os.environ.get("RATE_LIMIT_PER_MIN")
        os.environ["RATE_LIMIT_PER_MIN"] = "3"

    def tearDown(self):
        cache.clear()
        if self._prev is None:
            os.environ.pop("RATE_LIMIT_PER_MIN", None)
        else:
            os.environ["RATE_LIMIT_PER_MIN"] = self._prev

    def test_allows_up_to_limit_then_blocks(self):
        ip = "1.2.3.4"
        results = [check_rate_limit(ip) for _ in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_ips_are_independent(self):
        for _ in range(3):
            check_rate_limit("1.1.1.1")
        # a different IP still has its full budget
        self.assertTrue(check_rate_limit("2.2.2.2"))
