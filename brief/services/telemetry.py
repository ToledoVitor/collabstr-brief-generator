"""Token -> cost estimation.

Prices are approximate public list prices in USD per 1M tokens, kept in one
place. Matching is by substring so dated model ids (e.g. ...-20251001) resolve.
"""

from __future__ import annotations

# model id (substring) -> (input $/1M, output $/1M)
# Order matters: more specific ids must come BEFORE their prefixes, since
# _lookup() returns the first key that is a substring of the model id
# (e.g. "gpt-5-mini" must precede "gpt-5").
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}
DEFAULT_PRICE: tuple[float, float] = (1.00, 5.00)


def _lookup(model: str) -> tuple[float, float]:
    model = (model or "").lower()
    for key, price in PRICES.items():
        if key in model:
            return price
    return DEFAULT_PRICE


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _lookup(model)
    cost = input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price
    return round(cost, 6)
