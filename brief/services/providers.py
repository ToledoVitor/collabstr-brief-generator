"""Provider-agnostic LLM layer.

Each provider takes (system, user, json_schema) and returns a `ProviderResult`
with the parsed structured output plus token usage. The model id and provider
are chosen entirely from the environment — nothing here is hardcoded — so the
same code path runs OpenAI, Anthropic, or an offline `fake` provider.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

_TOOL_NAME = "emit_brief"
_TOOL_DESCRIPTION = "Return the campaign brief as structured fields."


@dataclass
class ProviderResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class LLMProvider(Protocol):
    def generate(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResult: ...


# OpenAI reasoning models (o-series, gpt-5 family) speak the Chat Completions API
# with two differences from classic models: they require `max_completion_tokens`
# (rejecting the legacy `max_tokens`) and accept only the default temperature
# (rejecting any explicit value). Detect them by model-id prefix.
_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _is_openai_reasoning_model(model: str) -> bool:
    return (model or "").lower().startswith(_OPENAI_REASONING_PREFIXES)


class OpenAIProvider:
    def __init__(self, model: str):
        from openai import OpenAI  # lazy import: only the chosen provider is required

        self.model = model
        self.client = OpenAI()

    def generate(self, system, user, schema, *, temperature, max_tokens):
        params = {
            "model": self.model,
            # All current chat models accept max_completion_tokens; reasoning
            # models reject the legacy max_tokens outright.
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": _TOOL_DESCRIPTION,
                        "parameters": schema,
                    },
                }
            ],
            # Force the function call so output is always structured JSON.
            "tool_choice": {"type": "function", "function": {"name": _TOOL_NAME}},
        }
        if _is_openai_reasoning_model(self.model):
            # Reasoning tokens count against max_completion_tokens. This is a
            # structured-extraction task, not a reasoning one — keep effort
            # minimal so the budget reaches the tool call instead of being spent
            # (and truncated) on hidden reasoning. These models also accept only
            # the default temperature, so it is omitted.
            params["reasoning_effort"] = "minimal"
        else:
            # Classic models honor the guardrail-clamped temperature.
            params["temperature"] = temperature
        resp = self.client.chat.completions.create(**params)

        choice = resp.choices[0]
        tool_calls = choice.message.tool_calls
        if not tool_calls:
            # Forced tool_choice but nothing returned — typically finish_reason
            # "length" (budget exhausted, often on reasoning tokens) or a refusal.
            # Surface it instead of a cryptic NoneType index error.
            raise RuntimeError(
                f"OpenAI returned no tool call (finish_reason={choice.finish_reason!r}); "
                "raise LLM_MAX_TOKENS or adjust the model."
            )
        data = json.loads(tool_calls[0].function.arguments)
        usage = resp.usage
        return ProviderResult(
            data=data,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            model=resp.model,
            provider="openai",
        )


class AnthropicProvider:
    def __init__(self, model: str):
        import anthropic  # lazy import

        self.model = model
        self.client = anthropic.Anthropic()

    def generate(self, system, user, schema, *, temperature, max_tokens):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": schema,
                }
            ],
            # Force tool use so output is always structured JSON.
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        usage = resp.usage
        return ProviderResult(
            data=dict(block.input),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model=resp.model,
            provider="anthropic",
        )


class FakeProvider:
    """Deterministic offline provider. Lets the app + tests run with no API key."""

    def __init__(self, model: str = "fake-model-1"):
        self.model = model

    def generate(self, system, user, schema, *, temperature, max_tokens):
        data = {
            "brief": (
                "Run a focused 3-week push pairing the brand's hero product with "
                "trusted creators. Prioritize native, platform-first storytelling "
                "over polished ads, and let creator voice carry the message."
            ),
            "angles": [
                {
                    "title": "Day-in-the-life integration",
                    "description": "Creators weave the product into a real daily routine to show authentic use.",
                },
                {
                    "title": "Before / after proof",
                    "description": "A fast, result-driven demo that makes the core benefit obvious in seconds.",
                },
                {
                    "title": "Creator's honest take",
                    "description": "An unscripted first-impression review that leans on creator trust over brand polish.",
                },
            ],
            "criteria": [
                "Hook lands within the first 3 seconds",
                "One clear, single call-to-action",
                "Native to the platform's format and current trends",
                "Partnership disclosed per FTC guidance",
            ],
        }
        # Rough token estimate (~4 chars/token) so telemetry is exercised offline.
        input_tokens = max(1, len(system) + len(user)) // 4
        output_tokens = max(1, len(json.dumps(data)) // 4)
        return ProviderResult(
            data=data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            provider="fake",
        )


def build_provider(provider: str | None = None, model: str | None = None) -> LLMProvider:
    """Construct the configured provider from env (or explicit args, for tests)."""
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).strip().lower()
    model = model or os.getenv("LLM_MODEL") or None

    if provider == "openai":
        return OpenAIProvider(model or "gpt-4o-mini")
    if provider == "anthropic":
        return AnthropicProvider(model or "claude-haiku-4-5")
    if provider == "fake":
        return FakeProvider(model or "fake-model-1")
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (use openai | anthropic | fake)")
