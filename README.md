# Collabstr — AI Brief Generator

A tiny, production-minded AI feature: from four inputs (brand, platform, goal, tone)
it generates a **campaign brief** — a short brief, 3–4 creative angles, and 3–5
success criteria — with **live latency / token / cost telemetry**.

Django + a provider-agnostic LLM layer (OpenAI · Anthropic · offline `fake`) and a
clean single-page jQuery front end.

## Quickstart

```bash
make install      # uv sync — creates .venv + installs deps
make migrate
make run          # http://127.0.0.1:8000  (default provider=fake works with NO API key)
make test         # offline test + eval suite
```

Use a real model: `cp .env.example .env`, then set `LLM_PROVIDER` (`anthropic` |
`openai`), `LLM_MODEL`, and the matching API key.

## Make targets

`make help` lists them all — `install`, `run`, `migrate`, `test`, `lint`, `fmt`,
`collectstatic`, `docker-build`, `docker-run`, `clean`.

## How it works

- **Endpoint** `POST /api/brief` → `{ result, telemetry }`.
- **Structured output** — the model is forced through a tool/function whose params
  are a JSON Schema (`brief`, `angles[]`, `criteria[]`); output is re-validated
  with Pydantic before returning.
- **Provider-agnostic** — `brief/services/providers.py`; provider + model are
  chosen entirely via env vars.
- **Guardrails** — enum allowlist on inputs, profanity filter, `temperature ≤ 0.5`,
  `max_tokens` cap, per-IP rate limit, output validation, no leaked internals.
- **Telemetry** — real provider token counts → USD cost, surfaced in the UI and
  persisted to a SQLite cost ledger (`BriefRequestLog`).

## Layout

```
briefgen/                 Django project (env-driven settings)
brief/views.py            HTTP: validate → rate-limit → guardrail → service → JSON
brief/schemas.py          Pydantic models + LLM JSON Schema (also source of form options)
brief/services/           llm orchestration · providers · guardrails · telemetry
brief/templates/
  base.html               shared shell (topbar, footer, blocks)
  components/             reusable partials: field, topbar, footer
  brief/index.html        the Brief Generator (extends base)
  brief/styleguide.html   living component reference
brief/static/brief/css/
  tokens.css              design tokens — single source of truth
  base.css                reset + layout primitives
  components.css          reusable components + variants
  pages.css               feature-specific styles
brief/tests/              offline eval harness + endpoint/page tests
```

## Design system

A small, dependency-free system built to scale as the repo grows:

- **Tokens** (`tokens.css`) are the single source of truth — colors, the Inter
  type scale, spacing scale, radii, shadow. Components never hardcode values.
- **Components** (`components.css`) follow a `.btn` / `.btn--primary` BEM-ish
  variant convention: buttons, pills, chips, banners, fields, cards.
- **Templates** use inheritance: every page extends `base.html` and composes
  partials from `components/`. Form `<option>`s are generated from the schema
  enums, so the UI and server-side allowlist can't drift.
- **`/styleguide`** renders every token + component variant on one page — the
  reference for building the next screen.

Tokens were extracted from Collabstr's production CSS (Inter · ink `#222` ·
pink `#FF899B` + the signature pink→purple gradient · 8px radius).

## Deploy

`Dockerfile` + `render.yaml` included (uv-based image; migrate + gunicorn + whitenoise).

On [Render](https://render.com): **New → Blueprint →** pick this repo **→ Apply**.
The blueprint is set up for a real **OpenAI** demo, so Render prompts for two
`sync: false` values at apply time:

- `OPENAI_API_KEY` — your key (kept out of git)
- `DJANGO_CSRF_TRUSTED_ORIGINS` — set to the full URL after the first deploy,
  e.g. `https://collabstr-brief-generator.onrender.com`

For a **keyless** demo instead, set `LLM_PROVIDER=fake` in the dashboard — the
page then runs with deterministic sample output and no key. Any Docker host
(Fly.io, Railway, Cloud Run) works the same way.
