"""Offline eval harness for the LLM service.

Runs the real orchestration path (prompt build -> provider -> schema validation
-> telemetry) against the deterministic FakeProvider, so it needs no API key and
is safe to run in CI. Golden inputs assert the *contract* holds, not exact prose.
"""

import os

from django.test import SimpleTestCase

from brief.schemas import BriefRequest, BriefResult
from brief.services.llm import _temperature, generate_brief
from brief.services.providers import FakeProvider, ProviderResult

GOLDEN_INPUTS = [
    {"brand": "Aera Skincare", "platform": "Instagram", "goal": "Awareness", "tone": "Friendly"},
    {"brand": "Northpeak Coffee", "platform": "TikTok", "goal": "Conversions", "tone": "Playful"},
    {"brand": "Lumen Audio", "platform": "UGC", "goal": "Content Assets", "tone": "Professional"},
]


class EvalContractTests(SimpleTestCase):
    def test_golden_inputs_satisfy_contract(self):
        for raw in GOLDEN_INPUTS:
            with self.subTest(brand=raw["brand"]):
                req = BriefRequest(**raw)
                result, telemetry = generate_brief(req, provider=FakeProvider())

                # Output shape
                self.assertIsInstance(result, BriefResult)
                self.assertTrue(result.brief.strip())
                self.assertTrue(3 <= len(result.angles) <= 4)
                self.assertTrue(3 <= len(result.criteria) <= 5)
                for angle in result.angles:
                    self.assertTrue(angle.title.strip())
                    self.assertTrue(angle.description.strip())

                # Telemetry present + sane
                for key in (
                    "provider",
                    "model",
                    "latency_ms",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cost_usd",
                ):
                    self.assertIn(key, telemetry)
                self.assertGreaterEqual(telemetry["cost_usd"], 0)
                self.assertEqual(
                    telemetry["total_tokens"],
                    telemetry["input_tokens"] + telemetry["output_tokens"],
                )

    def test_output_is_deterministic_for_same_inputs(self):
        req = BriefRequest(**GOLDEN_INPUTS[0])
        first, _ = generate_brief(req, provider=FakeProvider())
        second, _ = generate_brief(req, provider=FakeProvider())
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_malformed_model_output_is_rejected(self):
        """If a provider returns junk, schema validation must blow up (not pass it on)."""

        class BadProvider:
            def generate(self, *a, **k):
                return ProviderResult(
                    data={"brief": "ok", "angles": [{"title": "only one"}], "criteria": []},
                    input_tokens=1,
                    output_tokens=1,
                    model="bad",
                    provider="bad",
                )

        req = BriefRequest(**GOLDEN_INPUTS[0])
        with self.assertRaises(Exception):
            generate_brief(req, provider=BadProvider())


class GuardrailClampTests(SimpleTestCase):
    def test_temperature_is_clamped_to_ceiling(self):
        original = os.environ.get("LLM_TEMPERATURE")
        try:
            os.environ["LLM_TEMPERATURE"] = "2.0"
            self.assertLessEqual(_temperature(), 0.5)
            os.environ["LLM_TEMPERATURE"] = "0.2"
            self.assertEqual(_temperature(), 0.2)
        finally:
            if original is None:
                os.environ.pop("LLM_TEMPERATURE", None)
            else:
                os.environ["LLM_TEMPERATURE"] = original
