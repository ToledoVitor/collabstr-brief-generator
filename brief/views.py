"""HTTP layer. Thin: validate -> rate-limit -> guardrail -> service -> JSON.

Keeps no business logic of its own; everything substantive lives in services/.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from brief.models import BriefRequestLog
from brief.ratelimit import check_rate_limit
from brief.schemas import BriefRequest, Goal, Platform, Tone
from brief.services.guardrails import contains_profanity
from brief.services.llm import generate_brief

logger = logging.getLogger("brief")

_INPUT_FIELDS = ("brand", "platform", "goal", "tone")


def _form_options() -> dict:
    """Allowlisted dropdown values, single-sourced from the schema enums so the
    form and server-side validation can never drift apart."""
    return {
        "platforms": [p.value for p in Platform],
        "goals": [g.value for g in Goal],
        "tones": [t.value for t in Tone],
    }


@ensure_csrf_cookie
def index(request: HttpRequest):
    """Serve the single page and ensure the CSRF cookie is set for the AJAX call."""
    return render(request, "brief/index.html", _form_options())


def styleguide(request: HttpRequest):
    """Living component reference — design tokens + component variants."""
    return render(request, "brief/styleguide.html", {**_form_options(), "topbar_tag": "Styleguide"})


@require_POST
def create_brief(request: HttpRequest):
    client_ip = _client_ip(request)

    # 1) Rate limit (cheap, do it first).
    if not check_rate_limit(client_ip):
        return JsonResponse(
            {"error": "rate_limited", "detail": "Too many requests — try again in a minute."},
            status=429,
        )

    # 2) Parse body.
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "invalid_json", "detail": "Request body must be JSON."}, status=400
        )

    # 3) Validate + normalize inputs (allowlist enforced by enums in the schema).
    try:
        brief_request = BriefRequest(**{k: payload.get(k) for k in _INPUT_FIELDS})
    except ValidationError as exc:
        return JsonResponse({"error": "validation_error", "detail": _first_error(exc)}, status=400)

    # 4) Content guardrail on the only free-text field.
    if contains_profanity(brief_request.brand):
        return JsonResponse(
            {"error": "profanity", "detail": "Brand name failed the content filter."},
            status=400,
        )

    # 5) Call the model.
    try:
        result, telemetry = generate_brief(brief_request)
    except Exception:  # noqa: BLE001 — don't leak provider internals to the client
        logger.exception("brief generation failed")
        return JsonResponse(
            {
                "error": "llm_error",
                "detail": "The model call failed. Check the API key / server logs.",
            },
            status=502,
        )

    # 6) Persist the cost/latency ledger row.
    BriefRequestLog.objects.create(
        brand=brief_request.brand,
        platform=brief_request.platform.value,
        goal=brief_request.goal.value,
        tone=brief_request.tone.value,
        client_ip=client_ip,
        **{
            k: telemetry[k]
            for k in (
                "provider",
                "model",
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "cost_usd",
            )
        },
    )

    logger.info(
        "brief ok provider=%s model=%s latency_ms=%s tokens=%s cost_usd=%s",
        telemetry["provider"],
        telemetry["model"],
        telemetry["latency_ms"],
        telemetry["total_tokens"],
        telemetry["cost_usd"],
    )
    return JsonResponse({"result": result.model_dump(), "telemetry": telemetry})


def _client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    field = err.get("loc", ["input"])[0]
    msg = err.get("msg", "Invalid value.")
    return f"{field}: {msg}"
