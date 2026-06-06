"""Orchestration: build prompts -> call provider -> validate output -> telemetry.

This is the only place that knows the prompt and the guardrail clamps. Provider
specifics live in providers.py; cost math lives in telemetry.py.
"""

from __future__ import annotations

import os
import time

from brief.schemas import BRIEF_OUTPUT_SCHEMA, BriefRequest, BriefResult
from brief.services.observability import current_trace_id, observe_generation
from brief.services.providers import LLMProvider, build_provider
from brief.services.telemetry import estimate_cost

# Concise, deterministic system prompt: role, audience, style, hard constraints.
SYSTEM_PROMPT = (
    "You are a senior influencer-marketing strategist at Collabstr, a marketplace "
    "that connects brands with Instagram, TikTok, and UGC creators. "
    "Write a concise, practical campaign brief that a brand could hand to a creator today. "
    "Be specific and platform-aware. Match the requested tone exactly. "
    "Avoid hype, inflated claims, emojis, and hashtags. "
    "Return your answer ONLY through the emit_brief tool: a tight 2-4 sentence `brief`, "
    "3-4 distinct creative `angles` (each a short title + one-sentence description), and "
    "3-5 measurable success `criteria`."
)

# Hard ceilings enforced regardless of env (the assignment's guardrails).
MAX_TEMPERATURE = 0.5
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 900


def _user_prompt(req: BriefRequest) -> str:
    return (
        f"Brand: {req.brand}\n"
        f"Platform: {req.platform.value}\n"
        f"Goal: {req.goal.value}\n"
        f"Tone: {req.tone.value}\n"
        "Write the campaign brief now."
    )


def _temperature() -> float:
    try:
        requested = float(os.getenv("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    except ValueError:
        requested = DEFAULT_TEMPERATURE
    # Clamp to the guardrail ceiling.
    return max(0.0, min(requested, MAX_TEMPERATURE))


def _max_tokens() -> int:
    try:
        return int(os.getenv("LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    except ValueError:
        return DEFAULT_MAX_TOKENS


def generate_brief(
    req: BriefRequest, *, provider: LLMProvider | None = None
) -> tuple[BriefResult, dict]:
    """Return (validated result, telemetry dict). `provider` is injectable for tests."""
    provider = provider or build_provider()

    inputs = {
        "brand": req.brand,
        "platform": req.platform.value,
        "goal": req.goal.value,
        "tone": req.tone.value,
    }

    # Wrap the call as a Langfuse generation (no-op unless LANGFUSE_* is set).
    started = time.perf_counter()
    trace_id = None
    with observe_generation(
        name="generate_brief",
        model=os.getenv("LLM_MODEL") or None,
        input={"system": SYSTEM_PROMPT, "user": _user_prompt(req)},
        metadata=inputs,
    ) as gen:
        raw = provider.generate(
            SYSTEM_PROMPT,
            _user_prompt(req),
            BRIEF_OUTPUT_SCHEMA,
            temperature=_temperature(),
            max_tokens=_max_tokens(),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        # Trust nothing: validate the model output against our schema.
        result = BriefResult.model_validate(raw.data)
        cost_usd = estimate_cost(raw.model, raw.input_tokens, raw.output_tokens)

        if gen is not None:
            # Attach the resolved model, token usage and cost to the trace.
            gen.update(
                output=result.model_dump(),
                model=raw.model,
                usage_details={
                    "input": raw.input_tokens,
                    "output": raw.output_tokens,
                    "total": raw.input_tokens + raw.output_tokens,
                },
                cost_details={"total": cost_usd},
                metadata={**inputs, "provider": raw.provider},
            )
            trace_id = current_trace_id()

    telemetry = {
        "provider": raw.provider,
        "model": raw.model,
        "latency_ms": latency_ms,
        "input_tokens": raw.input_tokens,
        "output_tokens": raw.output_tokens,
        "total_tokens": raw.input_tokens + raw.output_tokens,
        "cost_usd": cost_usd,
    }

    if trace_id:
        telemetry["langfuse_trace_id"] = trace_id

    return result, telemetry
