# Collabstr — AI Brief Generator

A tiny, production-minded AI feature: from four inputs (brand, platform, goal, tone)
it generates a **campaign brief** — a short brief, 3–4 creative angles, and 3–5
success criteria — with **live latency / token / cost telemetry**.

Django + a provider-agnostic LLM layer (OpenAI · Anthropic · offline `fake`) and a
clean single-page jQuery front end.

## Live demo

- **App:** <!-- LIVE_URL --> _deploying…_ (`https://collabstr-brief-generator.onrender.com`)
- **Loom (< 1 min):** <!-- LOOM_URL --> _coming soon_
- **Styleguide:** `/styleguide` — living design-system reference

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

`Dockerfile` (uv image; migrate + gunicorn + whitenoise) + `railway.json` + `render.yaml`.

### Railway (recommended — persists data via a volume)

1. **New Project → Deploy from GitHub repo** → pick this repo. Railway builds the Dockerfile.
2. **Add a Volume** mounted at `/data` (so the SQLite cost ledger + share links survive redeploys).
3. **Settings → Networking → Generate Domain** → note the URL.
4. **Variables** — set:
   ```
   DJANGO_DEBUG=false
   DJANGO_SECRET_KEY=<long random string>
   DJANGO_ALLOWED_HOSTS=<your-domain>.up.railway.app
   DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-domain>.up.railway.app
   DJANGO_DB_PATH=/data/db.sqlite3
   LLM_PROVIDER=openai
   LLM_MODEL=gpt-5-mini
   OPENAI_API_KEY=<your key>
   ```
5. Redeploy. The start command migrates (creating the DB on the volume) then serves.

Keep **1 replica** (SQLite is single-writer). For multi-replica scale, switch to Postgres.

### Render (alt — blueprint)

**New → Blueprint →** pick repo **→ Apply**. `render.yaml` is wired for OpenAI and prompts
for `OPENAI_API_KEY` + `DJANGO_CSRF_TRUSTED_ORIGINS` at apply. Free tier has no persistent
disk, so the ledger/share links reset on redeploy unless you add a paid disk.

**Keyless demo** on either host: set `LLM_PROVIDER=fake` — deterministic output, no key.
