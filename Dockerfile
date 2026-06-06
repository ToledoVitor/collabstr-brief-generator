# Pinned by digest for reproducible builds. Bump periodically for base-OS CVEs:
#   docker manifest inspect python:3.12-slim | grep digest
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

# uv for dependency management (copied from the official image), version-pinned.
COPY --from=ghcr.io/astral-sh/uv:0.8.11@sha256:8101ad825250a114e7bef89eefaa73c31e34e10ffbe5aff01562740bac97553c /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install deps first (cached layer) from the lockfile — no dev deps.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Collect static at build time (whitenoise serves them in production).
# --no-dev keeps the runtime image free of dev tooling (ruff, pre-commit).
# DJANGO_DEBUG=true is set ONLY for this build step: real env vars (SECRET_KEY,
# ALLOWED_HOSTS) don't exist at build time, and prod settings fail closed without
# them. collectstatic just copies files, so the dev fallback is safe here; the
# runtime CMD below runs with the real DEBUG=false environment.
RUN DJANGO_DEBUG=true uv run --no-dev python manage.py collectstatic --noinput

EXPOSE 8000

# Migrate (creates the SQLite cost ledger), then serve with gunicorn.
CMD ["sh", "-c", "uv run --no-dev python manage.py migrate --noinput && uv run --no-dev gunicorn briefgen.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
