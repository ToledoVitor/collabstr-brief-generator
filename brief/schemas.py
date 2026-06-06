"""Typed contracts for the brief endpoint.

`BriefRequest`  — validates + normalizes the form inputs (allowlist via enums).
`BriefResult`   — validates the model's structured output before we trust it.
`BRIEF_OUTPUT_SCHEMA` — the JSON Schema we hand the LLM as a tool/function so
                        the output is deterministic in shape.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# ── Allowlisted inputs ────────────────────────────────────────────────────────
# Using enums means anything off-list is rejected by validation, for free.


class Platform(str, Enum):
    instagram = "Instagram"
    tiktok = "TikTok"
    ugc = "UGC"


class Goal(str, Enum):
    awareness = "Awareness"
    conversions = "Conversions"
    content_assets = "Content Assets"


class Tone(str, Enum):
    professional = "Professional"
    friendly = "Friendly"
    playful = "Playful"


_BRAND_ALLOWED = re.compile(r"^[\w &'.,\-!+]+$", re.UNICODE)


class BriefRequest(BaseModel):
    brand: str = Field(min_length=2, max_length=60)
    platform: Platform
    goal: Goal
    tone: Tone

    @field_validator("brand")
    @classmethod
    def normalize_brand(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if len(v) < 2:
            raise ValueError("Brand name is too short.")
        if not _BRAND_ALLOWED.match(v):
            raise ValueError("Brand name contains unsupported characters.")
        return v


# ── Structured model output ───────────────────────────────────────────────────


class Angle(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)


class BriefResult(BaseModel):
    brief: str = Field(min_length=1, max_length=1200)
    angles: list[Angle] = Field(min_length=3, max_length=4)
    criteria: list[str] = Field(min_length=3, max_length=5)

    @field_validator("criteria")
    @classmethod
    def clean_criteria(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c and c.strip()]
        if len(cleaned) < 3:
            raise ValueError("Need at least 3 non-empty criteria.")
        return cleaned


# JSON Schema handed to the LLM (OpenAI function params / Anthropic input_schema).
# Kept hand-written (not auto-derived) so it stays minimal and strict-mode safe.
BRIEF_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "brief": {
            "type": "string",
            "description": "A tight 2-4 sentence campaign brief.",
        },
        "angles": {
            "type": "array",
            "description": "3-4 distinct creative angles.",
            "minItems": 3,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short angle name."},
                    "description": {
                        "type": "string",
                        "description": "One sentence explaining the angle.",
                    },
                },
                "required": ["title", "description"],
                "additionalProperties": False,
            },
        },
        "criteria": {
            "type": "array",
            "description": "3-5 measurable success criteria.",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string"},
        },
    },
    "required": ["brief", "angles", "criteria"],
    "additionalProperties": False,
}
