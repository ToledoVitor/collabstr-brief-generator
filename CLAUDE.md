# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Django + jQuery AI feature: four inputs (brand, platform, goal, tone) → a campaign brief (short brief, 3–4 creative angles, 3–5 success criteria) with live latency/token/cost telemetry. Provider-agnostic LLM layer (OpenAI · Anthropic · offline `fake`).

## Commands

```bash
make install      # uv sync — creates .venv + installs deps
make migrate      # apply migrations (creates the SQLite cost ledger)
make run          # dev server at http://127.0.0.1:8000 (provider=fake, no key needed)
make test         # full test + eval suite (offline)
make lint         # ruff check
make fmt          # ruff format
```

All Python runs through `uv run`. `make help` lists every target.

**Tests must use the test settings** — they neutralize the LLM env so no real provider/key/network can leak in:

```bash
# Whole suite (this is what `make test` runs):
uv run python manage.py test --settings=briefgen.settings_test

# Single module / class / method:
uv run python manage.py test --settings=briefgen.settings_test brief.tests.test_views
uv run python manage.py test --settings=briefgen.settings_test brief.tests.test_views.BriefEndpointTests.test_happy_path_returns_result_and_telemetry
```

`briefgen/settings_test.py` pins `LLM_PROVIDER=fake` and strips `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` **at import time** (before any code reads them). Running `manage.py test` without `--settings=briefgen.settings_test` can hit a real provider — don't.

## Architecture

Everything operational (provider, model, keys, limits, temperature) is read from the **environment** — nothing is hardcoded. The same image runs locally and in production; only env vars change. `briefgen/settings.py` is intentionally minimal.

### Request flow (`POST /api/brief`)

`brief/views.py:create_brief` is a thin HTTP shell with **no business logic** — it only orchestrates, in this order:

1. **Rate limit** (`brief/ratelimit.py`) — per-IP, fixed 60s window via the Django cache. Cheap, done first.
2. **Parse** JSON body → 400 on bad JSON.
3. **Validate + normalize** inputs (`BriefRequest` in `brief/schemas.py`) — allowlist enforced by enums → 400 on failure.
4. **Guardrail** — profanity screen (`brief/services/guardrails.py`) on the only free-text field, `brand` → 400.
5. **Generate** (`brief/services/llm.py:generate_brief`) — any exception becomes a 502 with no provider internals leaked.
6. **Persist** a `BriefRequestLog` cost/latency ledger row, then return `{result, telemetry}`.

### Service layering — keep logic in its home

- `brief/services/llm.py` — orchestration. **The only place** that knows the system prompt and the guardrail clamps (`temperature ≤ 0.5`, `max_tokens` cap). Builds prompt → calls provider → re-validates output → assembles telemetry.
- `brief/services/providers.py` — **the only place** with SDK specifics. Each provider implements the `LLMProvider` protocol: `generate(system, user, schema, *, temperature, max_tokens) -> ProviderResult`. `build_provider()` selects from env. SDK imports are lazy (only the chosen provider is required).
- `brief/services/telemetry.py` — token→USD cost math. `PRICES` table keyed by model-id substring.
- `brief/schemas.py` — Pydantic contracts + the hand-written `BRIEF_OUTPUT_SCHEMA`.

### Structured output is the core pattern

The model is **forced** through a tool/function call (`emit_brief`) whose parameters are `BRIEF_OUTPUT_SCHEMA` (a JSON Schema), so output is always structured JSON — not free text. That raw output is then **re-validated with Pydantic** (`BriefResult.model_validate`) before it's trusted. Trust nothing from the model: malformed output raises and surfaces as a 502.

### Single sources of truth (don't let things drift)

- **Input options**: the `Platform` / `Goal` / `Tone` enums in `brief/schemas.py` drive *both* server-side validation *and* the form `<option>`s (via `views._form_options`). Add an allowed value by editing the enum — the dropdown and the allowlist update together.
- **Design tokens**: `brief/static/brief/css/tokens.css` holds all colors/type/spacing/radii. Components (`components.css`, BEM-ish `.btn` / `.btn--primary`) never hardcode values. `/styleguide` renders every token + variant — use it as the reference when building a new screen.

## Common changes

- **Add an LLM provider**: implement the `LLMProvider` protocol in `providers.py`, register it in `build_provider()`, add its model prices to `PRICES` in `telemetry.py`.
- **Add a brand/platform/goal/tone option**: edit the relevant enum in `schemas.py` (propagates to form + validation automatically).
- **Change a model/provider**: set `LLM_PROVIDER` / `LLM_MODEL` env vars — no code change. Cost math falls back to `DEFAULT_PRICE` for unknown models, but add a `PRICES` entry for accuracy.

## Conventions

- Python 3.12+, ruff (line-length 100, import sorting via `I`).
- `uv` for all dependency/run operations; this is an application, not a package (`package = false`).
- New tests go in `brief/tests/` and should run fully offline against `FakeProvider` (inject it: `generate_brief(req, provider=FakeProvider())`, or mock the SDK as in `test_views.py:MockedOpenAIEndpointTests`). No test should require a network call or API key.
