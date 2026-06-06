import secrets

from django.db import models

from brief.schemas import Goal, Platform, Tone


def _generate_public_id() -> str:
    """Short, URL-safe, unguessable id for shareable run links."""
    return secrets.token_urlsafe(12)


def _enum_choices(enum_cls) -> list[tuple[str, str]]:
    """Model `choices` derived from the schema enums — keeps the allowlist single-
    sourced (schemas.py) so the DB column can't represent a value the API rejects."""
    return [(member.value, member.value) for member in enum_cls]


class BriefRequestLog(models.Model):
    """One row per generated brief — a persisted cost/latency ledger.

    Lets you answer "what did we spend, how slow was it, what got asked for"
    without a separate analytics pipeline. Also backs shareable run links:
    each row has an unguessable `public_id` and stores the generated `result`,
    so GET /api/brief/<public_id> can replay any past run.
    """

    # Unguessable handle for the public share link (not the sequential pk).
    # unique=True already creates the lookup index used by GET /api/brief/<id>.
    public_id = models.CharField(
        max_length=24, unique=True, default=_generate_public_id, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Inputs (denormalized for easy querying / export). choices mirror the schema
    # enums so the column only ever holds an allowlisted value.
    brand = models.CharField(max_length=80)
    platform = models.CharField(max_length=20, choices=_enum_choices(Platform))
    goal = models.CharField(max_length=20, choices=_enum_choices(Goal))
    tone = models.CharField(max_length=20, choices=_enum_choices(Tone))

    # Telemetry. Token counts and latency are non-negative by nature.
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=80)
    latency_ms = models.PositiveIntegerField()
    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6)

    # The generated brief itself (brief / angles / criteria), so a shared link
    # can replay the exact run without re-calling the model.
    result = models.JSONField(default=dict)

    client_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Listing / time-series scans (matches the default ordering).
            models.Index(fields=["-created_at"], name="brief_created_idx"),
            # "what did each model cost / how much did we use it" analytics.
            models.Index(fields=["model"], name="brief_model_idx"),
            # Per-client lookups (abuse / usage by IP).
            models.Index(fields=["client_ip"], name="brief_client_ip_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.brand} · {self.platform} · {self.created_at:%Y-%m-%d %H:%M}"
