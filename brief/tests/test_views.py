"""Endpoint tests: validation, guardrails, rate limiting, persistence.

Uses LLM_PROVIDER=fake so no network/API key is involved.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from brief.models import BriefRequestLog

VALID = {"brand": "Aera Skincare", "platform": "Instagram", "goal": "Awareness", "tone": "Friendly"}

# A schema-valid model output, reused by the mocked-provider integration tests.
VALID_BRIEF = {
    "brief": "Run a focused 3-week creator push.",
    "angles": [
        {"title": "Day-in-the-life", "description": "Authentic routine integration."},
        {"title": "Before / after", "description": "Fast result-driven demo."},
        {"title": "Honest take", "description": "Unscripted first impression."},
    ],
    "criteria": ["Hook in 3s", "Single CTA", "Native to platform"],
}


class BriefEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self._prev_provider = os.environ.get("LLM_PROVIDER")
        os.environ["LLM_PROVIDER"] = "fake"
        self.url = reverse("create_brief")

    def tearDown(self):
        if self._prev_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = self._prev_provider

    def _post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def test_happy_path_returns_result_and_telemetry(self):
        resp = self._post(VALID)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertIn("result", body)
        self.assertIn("telemetry", body)
        self.assertTrue(body["result"]["brief"])
        self.assertTrue(3 <= len(body["result"]["angles"]) <= 4)
        self.assertTrue(3 <= len(body["result"]["criteria"]) <= 5)
        for key in ("latency_ms", "input_tokens", "output_tokens", "total_tokens", "cost_usd"):
            self.assertIn(key, body["telemetry"])

    def test_happy_path_persists_ledger_row(self):
        self.assertEqual(BriefRequestLog.objects.count(), 0)
        self._post(VALID)
        self.assertEqual(BriefRequestLog.objects.count(), 1)
        row = BriefRequestLog.objects.first()
        self.assertEqual(row.brand, "Aera Skincare")
        self.assertEqual(row.provider, "fake")

    def test_invalid_platform_is_rejected(self):
        resp = self._post({**VALID, "platform": "Facebook"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "validation_error")

    def test_short_brand_is_rejected(self):
        resp = self._post({**VALID, "brand": "A"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "validation_error")

    def test_profanity_brand_is_blocked(self):
        resp = self._post({**VALID, "brand": "Shitty Brand"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "profanity")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_rate_limit_kicks_in(self):
        prev = os.environ.get("RATE_LIMIT_PER_MIN")
        os.environ["RATE_LIMIT_PER_MIN"] = "3"
        try:
            statuses = [self._post(VALID).status_code for _ in range(4)]
        finally:
            if prev is None:
                os.environ.pop("RATE_LIMIT_PER_MIN", None)
            else:
                os.environ["RATE_LIMIT_PER_MIN"] = prev
        self.assertEqual(statuses[:3], [200, 200, 200])
        self.assertEqual(statuses[3], 429)


class PageRenderTests(TestCase):
    def test_index_renders_with_enum_options(self):
        resp = self.client.get(reverse("index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Brief Generator")
        # dropdown options are generated from the schema enums
        self.assertContains(resp, "Instagram")
        self.assertContains(resp, "Content Assets")

    def test_styleguide_renders(self):
        resp = self.client.get(reverse("styleguide"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Design System")


class MockedOpenAIEndpointTests(TestCase):
    """End-to-end through the REAL OpenAI provider code path — but the SDK is
    mocked, so there is NO network call and NO API key needed. This proves the
    provider wiring + structured-output parsing + persistence all work."""

    def setUp(self):
        cache.clear()
        self._saved = {k: os.environ.get(k) for k in ("LLM_PROVIDER", "LLM_MODEL")}
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_MODEL"] = "gpt-4o-mini"
        self.url = reverse("create_brief")

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _fake_openai_response(self):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(arguments=json.dumps(VALID_BRIEF))
                            )
                        ]
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=240),
            model="gpt-4o-mini",
        )

    def test_endpoint_uses_mocked_openai_and_persists(self):
        with patch("openai.OpenAI") as MockOpenAI:
            client = MockOpenAI.return_value
            client.chat.completions.create.return_value = self._fake_openai_response()

            resp = self.client.post(
                self.url, data=json.dumps(VALID), content_type="application/json"
            )

            # the only "external" call went to the mock — never the network
            client.chat.completions.create.assert_called_once()

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["telemetry"]["provider"], "openai")
        self.assertEqual(body["telemetry"]["input_tokens"], 120)
        self.assertEqual(body["telemetry"]["output_tokens"], 240)
        self.assertEqual(body["result"]["brief"], VALID_BRIEF["brief"])

        row = BriefRequestLog.objects.first()
        self.assertIsNotNone(row)
        self.assertEqual(row.provider, "openai")


class EndpointErrorPathTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("create_brief")

    def test_provider_failure_returns_502_and_writes_no_ledger(self):
        # Mock the service to blow up — no provider, no network involved.
        with patch("brief.views.generate_brief", side_effect=RuntimeError("boom")):
            resp = self.client.post(
                self.url, data=json.dumps(VALID), content_type="application/json"
            )
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.json()["error"], "llm_error")
        self.assertEqual(BriefRequestLog.objects.count(), 0)

    def test_invalid_json_body_returns_400(self):
        resp = self.client.post(self.url, data="{not valid json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_json")


class SharedRunTests(TestCase):
    """Server-backed shareable links: create returns an id; GET replays the run."""

    def setUp(self):
        cache.clear()
        os.environ["LLM_PROVIDER"] = "fake"

    def _create(self):
        return self.client.post(
            reverse("create_brief"), data=json.dumps(VALID), content_type="application/json"
        )

    def test_create_returns_id_and_persists_result(self):
        body = self._create().json()
        self.assertIn("id", body)
        self.assertTrue(body["id"])
        row = BriefRequestLog.objects.get(public_id=body["id"])
        # the generated brief is stored, not just telemetry
        self.assertEqual(row.result["brief"], body["result"]["brief"])
        self.assertEqual(len(row.result["angles"]), len(body["result"]["angles"]))

    def test_get_brief_replays_stored_run(self):
        created = self._create().json()
        resp = self.client.get(reverse("get_brief", args=[created["id"]]))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], created["id"])
        self.assertEqual(body["result"], created["result"])
        self.assertEqual(body["inputs"]["brand"], VALID["brand"])
        for key in ("provider", "model", "total_tokens", "cost_usd"):
            self.assertIn(key, body["telemetry"])

    def test_get_unknown_run_returns_404(self):
        resp = self.client.get(reverse("get_brief", args=["does-not-exist"]))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "not_found")
