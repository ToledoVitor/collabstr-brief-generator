import secrets

from django.db import models


def _generate_public_id() -> str:
    """Short, URL-safe, unguessable id for shareable run links."""
    return secrets.token_urlsafe(12)


class BriefRequestLog(models.Model):
    """One row per generated brief — a persisted cost/latency ledger.

    Lets you answer "what did we spend, how slow was it, what got asked for"
    without a separate analytics pipeline. Also backs shareable run links:
    each row has an unguessable `public_id` and stores the generated `result`,
    so GET /api/brief/<public_id> can replay any past run.
    """

    # Unguessable handle for the public share link (not the sequential pk).
    public_id = models.CharField(
        max_length=24, unique=True, default=_generate_public_id, editable=False, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Inputs (denormalized for easy querying / export)
    brand = models.CharField(max_length=80)
    platform = models.CharField(max_length=20)
    goal = models.CharField(max_length=20)
    tone = models.CharField(max_length=20)

    # Telemetry
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=80)
    latency_ms = models.IntegerField()
    input_tokens = models.IntegerField()
    output_tokens = models.IntegerField()
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6)

    # The generated brief itself (brief / angles / criteria), so a shared link
    # can replay the exact run without re-calling the model.
    result = models.JSONField(default=dict)

    client_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.brand} · {self.platform} · {self.created_at:%Y-%m-%d %H:%M}"
