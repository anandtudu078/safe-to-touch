"""Output contracts shared by the Gemini layer and the SSE endpoints.

These mirror the JSON the frontend renders (see frontend/app/page.tsx and
scripts/contract-check.mjs). Changing them means changing the UI contract too.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["Safe", "Risky", "Needs Review"]
Confidence = Literal["High", "Medium", "Low"]


class Evidence(BaseModel):
    history: str = Field(description="Commit lines + churn summary, 2-6 lines")
    docs: str = Field(description="Verbatim doc quote(s) with source file, 1-4 lines")
    dependents: str = Field(description="Dependent file + how it uses the target")
    tests: str = Field(description="Test files and what is asserted, or no-coverage note")


class CheckFindings(BaseModel):
    history: str
    docs: str
    dependents: str
    tests: str


class VerdictResult(BaseModel):
    """The investigate-safety card."""

    verdict: Verdict
    confidence: Confidence
    summary: str
    history: str
    docs: str
    dependents: str
    tests: str
    evidence: Evidence
    suggestions: list[str] = Field(default_factory=list, max_length=3)


class HeatmapFunction(BaseModel):
    name: str
    line: int
    verdict: Verdict
    confidence: Confidence
    reason: str


class HeatmapResult(BaseModel):
    """The whole-file risk heatmap card."""

    file: str
    functions: list[HeatmapFunction]
    summary: str


class CheckReports(BaseModel):
    """Raw evidence collected by the 4 deterministic checks."""

    history: str
    docs: str
    dependents: str
    tests: str
    inconclusive: list[str] = Field(default_factory=list)
