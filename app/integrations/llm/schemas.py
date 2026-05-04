from typing import Literal

from pydantic import BaseModel, Field


class GitHubUpdateSummary(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)
    breaking_changes: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
