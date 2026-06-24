"""Pydantic schema for LLM output — the first layer of the robustness stack.

Every conflict the model emits is parsed against these models before it is
cached or served. Required fields are enforced and ``severity`` is constrained
to a closed vocabulary, so prompt drift cannot silently corrupt stored results.
"""

from typing import Literal

from pydantic import BaseModel, field_validator


class ConflictSource(BaseModel):
    doc_id: str
    article: str
    quote: str = ""
    value: str | None = None


class Conflict(BaseModel):
    id: str
    title: str
    topic: str
    severity: Literal["critique", "majeur", "mineur"]
    type: Literal["contradiction", "lacune", "ambiguïté", "ambiguité"]
    description: str
    sources: list[ConflictSource]
    recommendation: str
    practical_impact: str | None = None
    quote_verified: bool = False

    @field_validator("severity", mode="before")
    @classmethod
    def normalise_severity(cls, v: str) -> str:
        return v.lower().strip()


class PairResult(BaseModel):
    conflicts: list[Conflict]
