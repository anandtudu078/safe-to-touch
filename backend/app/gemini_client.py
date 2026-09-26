"""Gemini layer: turns raw deterministic evidence into the structured cards.

The checks in checks.py gather facts with real git/grep. Gemini is used only
for what needs language: one-line findings, the merged verdict (applying the
same deterministic rules the Codebuff version used), and heatmap ranking.
"""

import os
from typing import Any

from pydantic import ValidationError

from .schemas import CheckReports, HeatmapResult, VerdictResult

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_VERDICT_RULES = """Apply these rules EXACTLY, in order:
RISKY if any of:
- Tests check: COVERED is no AND Dependents check: DEPENDENT_COUNT > 0
- History check: CHURN contains HOT or SUSPICIOUS: yes
- Docs check: STATUS is WARNED
SAFE if any of:
- Docs check: STATUS is DOCUMENTED_CURRENT AND Tests check: COVERED is yes or indirectly
- Dependents check: SELF_CONTAINED is yes AND Tests check: COVERED is not no AND Docs STATUS is not WARNED
- History check: CHURN is SINGLE_INTRO AND Dependents check: SELF_CONTAINED is yes
NEEDS REVIEW otherwise, and ALWAYS if 2+ reports are INCONCLUSIVE or reports conflict.
CONFIDENCE: High = all 4 reports concrete and the rule unambiguous; Medium = 1 inconclusive
or weaker rule combination; Low = 2+ inconclusive or target not located."""


def _client_and_model() -> tuple[Any, str]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/ "
            "and add it to .env, then restart the backend."
        )
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install -r backend/requirements.txt"
        ) from e
    client = genai.Client(api_key=api_key)
    return client, MODEL


def _generate_structured(client: Any, prompt: str, schema: dict) -> dict:
    from google.genai import types

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.1,
        ),
    )
    text = resp.text or ""
    import json

    return json.loads(text)


def _findings_prompt(reports: CheckReports) -> str:
    return (
        "You are the merger of a 'should I touch this' code investigation. "
        "Below are 4 deterministic check reports (git history, docs, dependents, tests).\n"
        f"{_VERDICT_RULES}\n\n"
        "For each of history/docs/dependents/tests write ONE short sentence (max ~20 words) "
        "summarizing that check's finding. If a report was INCONCLUSIVE, say so plainly.\n\n"
        "Also extract the raw evidence for drill-down:\n"
        "- history: the commit line(s) and CHURN line, verbatim\n"
        "- docs: the verbatim QUOTE and SOURCE\n"
        "- dependents: the DETAIL and BLAST_RADIUS lines\n"
        "- tests: the TEST_FILES and WHAT_ASSERTED lines (or the no-coverage statement)\n\n"
        "HISTORY REPORT:\n"
        f"{reports.history}\n\n"
        "DOCS REPORT:\n"
        f"{reports.docs}\n\n"
        "DEPENDENTS REPORT:\n"
        f"{reports.dependents}\n\n"
        "TESTS REPORT:\n"
        f"{reports.tests}\n\n"
        f"Inconclusive checks: {', '.join(reports.inconclusive) if reports.inconclusive else 'none'}\n"
    )


# ---- JSON schemas for Gemini structured output (openapi-ish subset it accepts)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["Safe", "Risky", "Needs Review"]},
        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "summary": {"type": "string"},
        "history": {"type": "string"},
        "docs": {"type": "string"},
        "dependents": {"type": "string"},
        "tests": {"type": "string"},
        "evidence": {
            "type": "object",
            "properties": {
                "history": {"type": "string"},
                "docs": {"type": "string"},
                "dependents": {"type": "string"},
                "tests": {"type": "string"},
            },
            "required": ["history", "docs", "dependents", "tests"],
        },
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict",
        "confidence",
        "summary",
        "history",
        "docs",
        "dependents",
        "tests",
        "evidence",
    ],
}

HEATMAP_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "functions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "line": {"type": "integer"},
                    "verdict": {
                        "type": "string",
                        "enum": ["Safe", "Risky", "Needs Review"],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["High", "Medium", "Low"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["name", "line", "verdict", "confidence", "reason"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["file", "functions", "summary"],
}

_ORDER = {"Risky": 0, "Needs Review": 1, "Safe": 2}


def merge_verdict(reports: CheckReports) -> VerdictResult:
    client, _ = _client_and_model()
    data = _generate_structured(client, _findings_prompt(reports), VERDICT_SCHEMA)
    try:
        return VerdictResult.model_validate(data)
    except ValidationError as e:
        # Fall back to a deterministic Needs Review card rather than failing.
        return VerdictResult(
            verdict="Needs Review",
            confidence="Low",
            summary="The merger returned a malformed result; review the evidence manually.",
            history=reports.history.splitlines()[0] if reports.history else "unknown",
            docs=reports.docs.splitlines()[0] if reports.docs else "unknown",
            dependents=reports.dependents.splitlines()[0] if reports.dependents else "unknown",
            tests=reports.tests.splitlines()[0] if reports.tests else "unknown",
            evidence={
                "history": reports.history,
                "docs": reports.docs,
                "dependents": reports.dependents,
                "tests": reports.tests,
            },
            suggestions=["Re-run the investigation; if it persists, inspect the reports below."],
        )


def rank_heatmap(file: str, reports_by_function: dict[str, CheckReports]) -> HeatmapResult:
    client, _ = _client_and_model()
    blocks = []
    for fname, reports in reports_by_function.items():
        blocks.append(
            f"FUNCTION: {fname}\nHISTORY:\n{reports.history}\nDOCS:\n{reports.docs}\n"
            f"DEPENDENTS:\n{reports.dependents}\nTESTS:\n{reports.tests}\n"
            f"Inconclusive: {', '.join(reports.inconclusive) or 'none'}"
        )
    prompt = (
        "You are the merger of a 'should I touch this' code investigation, "
        "ranking every function in one file.\n"
        f"{_VERDICT_RULES}\n\n"
        "For EACH function: give verdict, confidence, and a one-sentence reason "
        "citing its strongest evidence. Rank hottest first: Risky before "
        "Needs Review before Safe.\n\n"
        + "\n\n".join(blocks)
    )
    data = _generate_structured(client, prompt, HEATMAP_SCHEMA)
    data.setdefault("file", file)
    # Enforce deterministic ordering regardless of what the model returned.
    data["functions"] = sorted(
        data.get("functions", []),
        key=lambda f: (_ORDER.get(f.get("verdict", "Needs Review"), 1), -f.get("line", 0)),
    )
    return HeatmapResult.model_validate(data)


def friendly_error(err: Exception) -> str:
    msg = str(err)
    if "not set" in msg.lower():
        return msg  # already actionable (e.g. GEMINI_API_KEY is not set)
    if "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
        return (
            "Gemini free-tier quota exhausted for now. Wait a minute and retry, "
            "or check usage at https://aistudio.google.com/."
        )
    if "API_KEY" in msg or "401" in msg or "403" in msg:
        return (
            "Your GEMINI_API_KEY was rejected. Get a fresh free key at "
            "https://aistudio.google.com/ and update .env."
        )
    return msg
