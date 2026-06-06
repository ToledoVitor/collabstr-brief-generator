"""Input content guardrail: a lightweight profanity screen for free-text input.

This is intentionally small and illustrative. A production system should use a
maintained dataset / managed moderation service rather than a hardcoded list —
the goal here is to show the guardrail wired into the request path.

Platform / goal / tone are already allowlisted via enums in schemas.py, so this
only needs to screen the free-text `brand` field.
"""

from __future__ import annotations

import re

# Common profanity tokens. Not exhaustive by design (see module docstring).
_PROFANITY = {
    "fuck",
    "shit",
    "bitch",
    "bastard",
    "asshole",
    "dick",
    "piss",
    "cunt",
    "slut",
    "whore",
    "fag",
    "retard",
    "nigger",
    "nigga",
}

# Fold common leet substitutions so "sh1t" / "f@ck" don't slip through.
_LEET = str.maketrans(
    {"@": "a", "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s"}
)


def _normalize(text: str) -> str:
    return text.lower().translate(_LEET)


def contains_profanity(text: str) -> bool:
    norm = _normalize(text)

    # 1) word-boundary token match (low false-positive rate)
    tokens = re.findall(r"[a-z]+", norm)
    if any(t in _PROFANITY for t in tokens):
        return True

    # 2) catch spaced / punctuated evasion like "f u c k" by collapsing
    collapsed = re.sub(r"[^a-z]", "", norm)
    return any(p in collapsed for p in _PROFANITY if len(p) >= 4)
