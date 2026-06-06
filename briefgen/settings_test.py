"""Test settings: fully isolated from the developer's ambient environment.

Imported via `manage.py test --settings=briefgen.settings_test`. Two jobs:

1. Neutralize the LLM env AT IMPORT TIME so no real provider/model/key can leak
   into the suite — the default provider becomes the offline `fake` one, and any
   stray OpenAI/Anthropic keys are stripped before code ever reads them.
2. Keep test output quiet: silence the `brief` logger (including the intentional
   `logger.exception` traceback in the 502 path) and drop WhiteNoise so the
   "No directory at: .../staticfiles/" UserWarning never fires.

Production settings (briefgen/settings.py) are left untouched.
"""

import os

# 1) Neutralize LLM env before anything reads it. build_provider() defaults to
#    `anthropic` when LLM_PROVIDER is unset, so pinning it to `fake` here is what
#    guarantees an unmocked default path can never reach a real SDK / network.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["LLM_MODEL"] = "test-model"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

# Django security settings fail closed in prod (DEBUG off → SECRET_KEY/ALLOWED_HOSTS
# required, SSL redirect on). Pin a dev-like posture for the offline suite so importing
# settings doesn't raise and the test client (host "testserver") isn't redirected to
# https. setdefault so an explicit ambient value still wins.
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-real-secret")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

from .settings import *  # noqa: E402,F401,F403

# 2a) Drop WhiteNoise: it's a production static-file concern and emits a
#     UserWarning at startup when STATIC_ROOT hasn't been collected.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m.lower()]  # noqa: F405

# 2b) Quiet the `brief` logger so the intentional ERROR traceback (502 test) and
#     the INFO "brief ok" lines don't pollute test output.
LOGGING = {  # noqa: F405
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "brief": {"handlers": [], "level": "CRITICAL", "propagate": False},
    },
}
