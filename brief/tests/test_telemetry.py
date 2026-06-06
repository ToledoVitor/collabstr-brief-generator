"""Unit tests for token -> cost estimation."""

from django.test import SimpleTestCase

from brief.services.telemetry import DEFAULT_PRICE, PRICES, _lookup, estimate_cost


class TelemetryTests(SimpleTestCase):
    def test_known_model_cost(self):
        # gpt-4o-mini = ($0.15, $0.60) per 1M -> 1M in + 1M out = 0.75
        self.assertAlmostEqual(estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000), 0.75)

    def test_substring_match_with_date_suffix(self):
        self.assertEqual(_lookup("gpt-4o-mini-2024-07-18"), PRICES["gpt-4o-mini"])

    def test_unknown_model_falls_back_to_default(self):
        self.assertEqual(_lookup("gemini-1.5-pro"), DEFAULT_PRICE)
        self.assertEqual(_lookup(""), DEFAULT_PRICE)

    def test_specific_model_id_wins_over_prefix(self):
        # "gpt-5-mini" must NOT resolve to the generic "gpt-5" price.
        self.assertEqual(_lookup("gpt-5-mini-2025-08"), PRICES["gpt-5-mini"])
        self.assertEqual(_lookup("gpt-5-2025-08"), PRICES["gpt-5"])

    def test_zero_tokens_is_zero_cost(self):
        self.assertEqual(estimate_cost("claude-haiku-4-5", 0, 0), 0.0)

    def test_rounded_to_six_dp(self):
        cost = estimate_cost("gpt-4o-mini", 161, 200)
        self.assertEqual(cost, round(161 / 1e6 * 0.15 + 200 / 1e6 * 0.60, 6))
