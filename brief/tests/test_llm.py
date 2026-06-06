"""Unit tests for the LLM orchestration layer.

A mock provider is injected, so no real OpenAI/Anthropic call happens. These
tests cover prompt assembly, the temperature guardrail clamp, telemetry
assembly, and output validation.
"""

import os
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from brief.schemas import BriefRequest, BriefResult
from brief.services.llm import SYSTEM_PROMPT, generate_brief
from brief.services.providers import ProviderResult

VALID_DATA = {
    "brief": "Tight brief.",
    "angles": [
        {"title": "A", "description": "a"},
        {"title": "B", "description": "b"},
        {"title": "C", "description": "c"},
    ],
    "criteria": ["one", "two", "three"],
}


def make_provider(data=None, input_tokens=100, output_tokens=200, model="mock-1"):
    provider = MagicMock()
    provider.generate.return_value = ProviderResult(
        data=data or VALID_DATA,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        provider="mock",
    )
    return provider


class GenerateBriefTests(SimpleTestCase):
    def setUp(self):
        self.req = BriefRequest(
            brand="Aera", platform="Instagram", goal="Awareness", tone="Friendly"
        )

    def test_returns_validated_result_and_telemetry(self):
        provider = make_provider()
        result, telemetry = generate_brief(self.req, provider=provider)

        self.assertIsInstance(result, BriefResult)
        provider.generate.assert_called_once()
        self.assertEqual(telemetry["provider"], "mock")
        self.assertEqual(telemetry["total_tokens"], 300)
        self.assertIn("latency_ms", telemetry)
        self.assertGreaterEqual(telemetry["latency_ms"], 0)
        self.assertGreaterEqual(telemetry["cost_usd"], 0)

    def test_temperature_clamped_and_prompts_passed(self):
        prev = os.environ.get("LLM_TEMPERATURE")
        os.environ["LLM_TEMPERATURE"] = "2.0"  # above the 0.5 ceiling
        try:
            provider = make_provider()
            generate_brief(self.req, provider=provider)
        finally:
            if prev is None:
                os.environ.pop("LLM_TEMPERATURE", None)
            else:
                os.environ["LLM_TEMPERATURE"] = prev

        args, kwargs = provider.generate.call_args
        self.assertLessEqual(kwargs["temperature"], 0.5)
        self.assertEqual(args[0], SYSTEM_PROMPT)  # system prompt
        self.assertIn("Aera", args[1])  # user prompt has the brand
        self.assertIn("Instagram", args[1])

    def test_malformed_provider_output_raises(self):
        provider = make_provider(data={"brief": "x", "angles": [], "criteria": []})
        with self.assertRaises(Exception):
            generate_brief(self.req, provider=provider)
