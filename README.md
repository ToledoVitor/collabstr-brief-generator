# Collabstr — AI Brief Generator

**Four inputs → a ready-to-send campaign brief, with live token / latency / cost telemetry.**

Type a brand, pick a platform, goal, and tone; get back a short brief, 3–4 creative
angles, and 3–5 measurable success criteria. Behind it: Django, a provider-agnostic
LLM layer (OpenAI · Anthropic · offline `fake`), and a single jQuery page styled from
Collabstr's own design tokens. Built in about an hour.

## Live demo

- **App:** <!-- LIVE_URL --> **https://collabstr-brief-generator-production.up.railway.app**
- **Loom (< 1 min):** <!-- LOOM_URL --> **https://www.loom.com/share/1a4c6b5fe6d9403797a0696be2cd8747**
- **Styleguide:** [`/styleguide`](https://collabstr-brief-generator-production.up.railway.app/styleguide) — living design-system reference

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

## Developing process

Built in one session with Claude Code — four commits over ~30 minutes
([history](https://github.com/ToledoVitor/collabstr-brief-generator/commits/main)).
The order was on purpose: prove the risky parts first, polish second, deploy last.

1. **Vertical slice before polish.** Form → endpoint → model → rendered brief, working
   end to end in the first commit. I wanted structured output and telemetry proven
   before spending a minute on CSS.

2. **An offline `fake` provider.** The app and the *whole* test suite run with no API
   key. The LLM layer is a Protocol with three implementations (OpenAI · Anthropic ·
   `fake`), chosen by an env var; `fake` returns a fixed brief. So `make run` and
   `make test` need zero setup, CI never needs a secret, and tests inject
   `FakeProvider()` directly. This one decision shaped the rest of the layering.

3. **Force structure, then distrust it.** The model can only answer through a function
   call (`emit_brief`) whose parameters are a JSON Schema — I get JSON, not prose to
   parse. But I don't trust that JSON either: it's re-validated with Pydantic before
   the view sees it, so malformed output becomes a clean 502 instead of a half-rendered
   page.

4. **A prompt that's short, specific, and clamped.** One system prompt: the role
   (Collabstr strategist), the platforms, hard style rules (no hype, emojis, or
   hashtags), and the exact fields to emit. The user prompt is just the four inputs.
   Temperature defaults to 0.3 and is clamped to ≤0.5 *in code*, so an env override
   can't push it higher.

5. **One home per decision, so nothing drifts.** Guardrail clamps live only in
   `llm.py`; SDK quirks only in `providers.py`; the input allowlist is the `schemas.py`
   enums — which also generate the form's dropdown options, so the UI and the
   server-side validation can never disagree. Adding a tone is a one-line enum edit.

6. **Went past the brief on purpose.** Persistence wasn't required, but telemetry that
   vanishes on refresh felt half-finished. So every run is logged to a small SQLite
   cost/latency ledger and gets an unguessable share link (`?run=<id>`). Deploy came
   last: a hardened `--no-dev` image, then Railway with a volume so the ledger survives
   redeploys.

**How tokens and latency are measured.** Tokens come straight from each provider's own
`usage` (prompt/completion counts) — not estimated; the `fake` provider approximates at
~4 chars/token so the numbers still move offline. Latency is wall-clock
`time.perf_counter()` wrapped around the provider call only, in
[`llm.py`](brief/services/llm.py). Cost is `tokens × per-model price` from a small table
in [`telemetry.py`](brief/services/telemetry.py). All three ride back in the response
JSON and render as chips in the UI.

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

Containerized (`Dockerfile`: uv image, migrate + gunicorn + whitenoise) with a
`railway.json` for setup. Running live on **Railway**.

1. **New Project → Deploy from GitHub repo** → pick this repo (it builds the Dockerfile).
2. **Add a Volume** mounted at `/data` — the SQLite cost ledger and the shareable
   run links live here, so they survive redeploys.
3. **Settings → Networking → Generate Domain.**
4. **Variables** — the host and CSRF origin are read automatically from Railway's
   `RAILWAY_PUBLIC_DOMAIN`, so you only need:
   ```
   DJANGO_DEBUG=false
   DJANGO_SECRET_KEY=<long random string>
   DJANGO_DB_PATH=/data/db.sqlite3
   LLM_PROVIDER=openai
   LLM_MODEL=gpt-5-mini
   OPENAI_API_KEY=<your key>
   ```
5. Deploy. The start command migrates (creating the DB on the volume) then serves.

Keep **1 replica** (SQLite is single-writer); switch to Postgres to scale out.
Keyless demo: set `LLM_PROVIDER=fake` for deterministic output with no key.

## A note on how this was built

Quick bit of honesty: I built this with Claude Code (Opus 4.8) doing most of the
typing while I did home chores. Start to finish it was about **1h10** — a little over the
one-hour target in the brief, but I'd rather hand over a clean, tested slice than
rush it.

A word on hosting, since the brief leaves it open: I went with Railway over Render,
mostly for persistence. The app keeps a small SQLite ledger and every brief gets a
shareable link that replays the exact run, so I wanted that data to stick around.
Railway lets you mount a volume and put SQLite on it, so runs survive redeploys.
Render's free tier also sleeps when idle (a cold start every time someone opens a
shared link), and Railway's trial credit avoids that. I'd been meaning to try
Railway anyway, so this was a good excuse. And also, I'm using my free trial to
do that 😉)
