FROM python:3.12-slim

# uv for dependency management (copied from the official image).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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
RUN uv run python manage.py collectstatic --noinput

EXPOSE 8000

# Migrate (creates the SQLite cost ledger), then serve with gunicorn.
CMD ["sh", "-c", "uv run python manage.py migrate --noinput && uv run gunicorn briefgen.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
