"""Unit tests for the provider layer.

CRITICAL: the OpenAI and Anthropic SDKs are MOCKED here — no network call and no
API key is ever required. Each test patches the SDK class and asserts the
provider builds the request correctly and parses the (fake) response.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from brief.services.providers import (
    AnthropicProvider,
    FakeProvider,
    OpenAIProvider,
    ProviderResult,
    build_provider,
)

VALID_DATA = {
    "brief": "Tight brief.",
    "angles": [
        {"title": "A", "description": "a"},
        {"title": "B", "description": "b"},
        {"title": "C", "description": "c"},
    ],
    "criteria": ["one", "two", "three"],
}


class BuildProviderTests(SimpleTestCase):
    def setUp(self):
        # Isolate from any LLM_PROVIDER / LLM_MODEL in the ambient environment.
        self._saved = {k: os.environ.pop(k, None) for k in ("LLM_PROVIDER", "LLM_MODEL")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_fake_provider(self):
        self.assertIsInstance(build_provider("fake"), FakeProvider)

    def test_openai_default_model(self):
        with patch("openai.OpenAI"):
            p = build_provider("openai")
        self.assertIsInstance(p, OpenAIProvider)
        self.assertEqual(p.model, "gpt-4o-mini")

    def test_anthropic_default_model(self):
        with patch("anthropic.Anthropic"):
            p = build_provider("anthropic")
        self.assertIsInstance(p, AnthropicProvider)
        self.assertEqual(p.model, "claude-haiku-4-5")

    def test_explicit_model_wins(self):
        with patch("anthropic.Anthropic"):
            p = build_provider("anthropic", "claude-custom")
        self.assertEqual(p.model, "claude-custom")

    def test_env_drives_provider_and_model(self):
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_MODEL"] = "gpt-4.1-mini"
        with patch("openai.OpenAI"):
            p = build_provider()
        self.assertIsInstance(p, OpenAIProvider)
        self.assertEqual(p.model, "gpt-4.1-mini")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            build_provider("gemini")


class OpenAIProviderTests(SimpleTestCase):
    def _fake_response(self):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(arguments=json.dumps(VALID_DATA))
                            )
                        ]
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=456),
            model="gpt-4o-mini-2024-07-18",
        )

    def test_generate_parses_and_maps_usage_without_network(self):
        with patch("openai.OpenAI") as MockOpenAI:
            client = MockOpenAI.return_value
            client.chat.completions.create.return_value = self._fake_response()

            provider = OpenAIProvider("gpt-4o-mini")
            result = provider.generate(
                "system", "user", {"type": "object"}, temperature=0.3, max_tokens=900
            )

            client.chat.completions.create.assert_called_once()
            kwargs = client.chat.completions.create.call_args.kwargs

        self.assertIsInstance(result, ProviderResult)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.data, VALID_DATA)
        self.assertEqual(result.input_tokens, 123)
        self.assertEqual(result.output_tokens, 456)
        self.assertEqual(result.model, "gpt-4o-mini-2024-07-18")
        # request shape: forced function call + passthrough sampling params
        self.assertEqual(kwargs["temperature"], 0.3)
        self.assertEqual(kwargs["max_completion_tokens"], 900)
        self.assertEqual(
            kwargs["tool_choice"], {"type": "function", "function": {"name": "emit_brief"}}
        )

    def test_reasoning_model_omits_temperature_and_uses_completion_tokens(self):
        """gpt-5 / o-series reject the legacy max_tokens and any explicit temperature."""
        with patch("openai.OpenAI") as MockOpenAI:
            client = MockOpenAI.return_value
            client.chat.completions.create.return_value = self._fake_response()

            OpenAIProvider("gpt-5-mini").generate(
                "system", "user", {"type": "object"}, temperature=0.3, max_tokens=900
            )
            kwargs = client.chat.completions.create.call_args.kwargs

        self.assertEqual(kwargs["max_completion_tokens"], 900)
        self.assertEqual(kwargs["reasoning_effort"], "minimal")
        self.assertNotIn("max_tokens", kwargs)
        self.assertNotIn("temperature", kwargs)

    def test_missing_tool_call_raises_clear_error(self):
        """No tool call (e.g. budget spent on reasoning) must raise, not index None."""
        no_call = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(tool_calls=None), finish_reason="length")
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            model="gpt-5-mini",
        )
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = no_call
            with self.assertRaises(RuntimeError):
                OpenAIProvider("gpt-5-mini").generate(
                    "s", "u", {"type": "object"}, temperature=0.3, max_tokens=900
                )


class AnthropicProviderTests(SimpleTestCase):
    def _fake_response(self):
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="ignored"),
                SimpleNamespace(type="tool_use", input=VALID_DATA),
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
            model="claude-haiku-4-5",
        )

    def test_generate_parses_and_maps_usage_without_network(self):
        with patch("anthropic.Anthropic") as MockAnthropic:
            client = MockAnthropic.return_value
            client.messages.create.return_value = self._fake_response()

            provider = AnthropicProvider("claude-haiku-4-5")
            result = provider.generate(
                "system", "user", {"type": "object"}, temperature=0.5, max_tokens=800
            )

            client.messages.create.assert_called_once()
            kwargs = client.messages.create.call_args.kwargs

        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.data, VALID_DATA)
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 20)
        self.assertEqual(kwargs["tool_choice"], {"type": "tool", "name": "emit_brief"})
        self.assertEqual(kwargs["max_tokens"], 800)


class FakeProviderTests(SimpleTestCase):
    def test_returns_valid_shape_and_positive_tokens(self):
        result = FakeProvider().generate("sys", "usr", {}, temperature=0.3, max_tokens=900)
        self.assertEqual(result.provider, "fake")
        self.assertEqual(len(result.data["angles"]), 3)
        self.assertEqual(len(result.data["criteria"]), 4)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)
