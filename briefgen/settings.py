"""Django settings for the Collabstr AI Brief Generator.

Intentionally small. Everything operational (provider, model, keys, limits) is
read from the environment so the same image runs locally and in production.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env early so both Django and the LLM service see the same environment.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# Fail closed: debug must be opted into explicitly, never the default in prod.
DEBUG = _env_bool("DJANGO_DEBUG", "false")

# A known SECRET_KEY lets an attacker forge CSRF tokens (Django derives them from
# it). Allow the insecure dev fallback ONLY under DEBUG; require a real key in prod.
_DEV_SECRET = "dev-insecure-change-me"  # dev-only sentinel; prod must override
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", _DEV_SECRET if DEBUG else "")
if not DEBUG and (not SECRET_KEY or SECRET_KEY == _DEV_SECRET):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG is off."
    )

# Host allowlist. No insecure '*' default: dev falls back to localhost, prod must
# set real hosts so a missing value fails closed instead of disabling Host checks.
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    if DEBUG:
        ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
    else:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set when DJANGO_DEBUG is off.")

# Trust the deploy origin for CSRF when hosting behind HTTPS (e.g. *.onrender.com).
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Respect the proxy's forwarded scheme so request.is_secure() / CSRF / SSL redirect
# work behind a TLS-terminating load balancer (Render, Fly, etc.). Trustworthy ONLY
# behind a proxy that sets X-Forwarded-Proto and strips any client-supplied copy;
# do not rely on it if the app is reachable directly.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Production transport hardening (no-ops in local DEBUG over plain HTTP).
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "brief",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "briefgen.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
            ],
        },
    },
]

WSGI_APPLICATION = "briefgen.wsgi.application"

# SQLite path is env-overridable so it can live on a mounted persistent volume
# in production (e.g. a Railway/Fly volume at /data) and survive redeploys.
# Local/dev falls back to the project directory.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DJANGO_DB_PATH") or (BASE_DIR / "db.sqlite3"),
    }
}

# Per-IP rate limiting uses the cache. LocMem is fine for a single instance;
# swap in Redis for multi-process / multi-instance deployments.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "kv": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "kv"},
    },
    "loggers": {
        "brief": {"handlers": ["console"], "level": "INFO"},
    },
}
