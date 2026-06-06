"""Optional Langfuse tracing for the generation step.

A thin, fail-open wrapper around the Langfuse SDK. It is a **no-op unless**
`LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` are set (and `LANGFUSE_TRACING`
isn't turned off), so the offline `fake` path and the test suite never import
the SDK or touch the network — mirroring the lazy-import discipline used for the
provider SDKs in providers.py.

Tracing must never break a brief: every Langfuse call here is guarded, and any
failure is logged and swallowed.

Config (read from the environment, like everything else):
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_SECRET_KEY   sk-lf-...
    LANGFUSE_BASE_URL     e.g. https://us.cloud.langfuse.com   (SDK default if unset)
    LANGFUSE_TRACING      "false" to force-disable even when keys are present
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger("brief")

_client = None
_resolved = False


def _disabled_by_flag() -> bool:
    return os.getenv("LANGFUSE_TRACING", "true").strip().lower() in {"0", "false", "no", "off"}


def is_enabled() -> bool:
    """True only when credentials are present and tracing isn't disabled."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")) and (
        not _disabled_by_flag()
    )


def get_client():
    """Return a cached Langfuse client, or None when tracing is off.

    The SDK reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL
    from the environment. Imported lazily so it isn't a hard dependency of the
    offline path.
    """
    global _client, _resolved
    if not is_enabled():
        return None
    if not _resolved:
        _resolved = True
        try:
            from langfuse import get_client as _get_client  # lazy import

            _client = _get_client()
        except Exception:  # noqa: BLE001 — tracing must never break generation
            logger.exception("langfuse init failed; tracing disabled")
            _client = None
    return _client


@contextmanager
def observe_generation(*, name: str, model: str | None, input, metadata: dict):
    """Record the LLM call as a Langfuse 'generation' observation.

    Yields the generation handle (call `.update(...)` on it to attach output,
    usage_details and cost_details), or None when tracing is off. The span times
    the wrapped block automatically. All tracing errors are swallowed.
    """
    client = get_client()
    if client is None:
        yield None
        return

    cm = gen = None
    try:
        cm = client.start_as_current_observation(
            as_type="generation", name=name, model=model, input=input, metadata=metadata
        )
        gen = cm.__enter__()
    except Exception:  # noqa: BLE001
        logger.exception("langfuse start failed; continuing without tracing")
        yield None
        return

    try:
        yield gen
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            logger.exception("langfuse end failed")


def current_trace_id() -> str | None:
    """Trace id of the active span — call inside `observe_generation`. None if off."""
    client = get_client()
    if client is None:
        return None
    try:
        return client.get_current_trace_id()
    except Exception:  # noqa: BLE001
        return None
