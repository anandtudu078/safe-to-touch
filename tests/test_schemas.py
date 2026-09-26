"""Tests for backend/app/schemas.py — pydantic model validation."""

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    CheckReports,
    Evidence,
    HeatmapFunction,
    HeatmapResult,
    VerdictResult,
)


# ---------------------------------------------------------------------------
# CheckReports
# ---------------------------------------------------------------------------

class TestCheckReports:
    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            CheckReports(history="h", docs="d", dependents="dep")  # missing tests

    def test_inconclusive_defaults_to_empty(self):
        r = CheckReports(history="h", docs="d", dependents="dep", tests="t")
        assert r.inconclusive == []

    def test_inconclusive_accepts_list(self):
        r = CheckReports(
            history="h", docs="d", dependents="dep", tests="t",
            inconclusive=["history", "docs"],
        )
        assert r.inconclusive == ["history", "docs"]

    def test_round_trip_json(self):
        r = CheckReports(history="h", docs="d", dependents="dep", tests="t")
        restored = CheckReports.model_validate_json(r.model_dump_json())
        assert restored == r


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class TestEvidence:
    def test_all_fields_required(self):
        # Evidence fields are required strings per the schema definition
        with pytest.raises(ValidationError):
            Evidence()

    def test_full_evidence(self):
        e = Evidence(history="h", docs="d", dependents="dep", tests="t")
        assert e.history == "h"


# ---------------------------------------------------------------------------
# VerdictResult
# ---------------------------------------------------------------------------

class TestVerdictResult:
    def _base(self, **overrides):
        base = dict(
            verdict="Safe",
            confidence="High",
            summary="Looks fine.",
            history="1 commit",
            docs="documented",
            dependents="none",
            tests="covered",
            evidence=Evidence(history="raw", docs="raw", dependents="raw", tests="raw"),
        )
        base.update(overrides)
        return VerdictResult(**base)

    def test_valid_safe(self):
        r = self._base()
        assert r.verdict == "Safe"
        assert r.confidence == "High"

    def test_valid_risky(self):
        r = self._base(verdict="Risky", confidence="Medium")
        assert r.verdict == "Risky"

    def test_valid_needs_review(self):
        r = self._base(verdict="Needs Review", confidence="Low")
        assert r.verdict == "Needs Review"

    def test_invalid_verdict_rejected(self):
        with pytest.raises(ValidationError):
            self._base(verdict="Unknown")

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValidationError):
            self._base(confidence="Very High")

    def test_suggestions_defaults_to_empty(self):
        r = self._base()
        assert r.suggestions == []

    def test_suggestions_max_three(self):
        # max_length=3 on the field
        with pytest.raises(ValidationError):
            self._base(suggestions=["a", "b", "c", "d"])

    def test_model_dump_has_all_keys(self):
        r = self._base()
        d = r.model_dump()
        for key in ("verdict", "confidence", "summary", "history", "docs",
                    "dependents", "tests", "evidence", "suggestions"):
            assert key in d


# ---------------------------------------------------------------------------
# HeatmapFunction
# ---------------------------------------------------------------------------

class TestHeatmapFunction:
    def test_valid(self):
        f = HeatmapFunction(
            name="parseDateString", line=5,
            verdict="Risky", confidence="High",
            reason="Hot churn + no tests",
        )
        assert f.name == "parseDateString"
        assert f.line == 5

    def test_invalid_verdict(self):
        with pytest.raises(ValidationError):
            HeatmapFunction(name="f", line=1, verdict="Bad", confidence="High", reason="r")

    def test_invalid_confidence(self):
        with pytest.raises(ValidationError):
            HeatmapFunction(name="f", line=1, verdict="Safe", confidence="Extreme", reason="r")


# ---------------------------------------------------------------------------
# HeatmapResult
# ---------------------------------------------------------------------------

class TestHeatmapResult:
    def test_empty_functions(self):
        r = HeatmapResult(file="src/date.ts", functions=[], summary="No functions found.")
        assert r.functions == []

    def test_with_functions(self):
        r = HeatmapResult(
            file="src/date.ts",
            functions=[
                HeatmapFunction(name="f", line=1, verdict="Safe",
                                confidence="High", reason="ok"),
            ],
            summary="One function.",
        )
        assert len(r.functions) == 1
        assert r.functions[0].name == "f"
