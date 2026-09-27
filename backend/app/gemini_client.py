"""Gemini layer: turns raw deterministic evidence into the structured cards.

The checks in checks.py gather facts with real git/grep. Gemini is used only
for what needs language: one-line findings, the merged verdict (applying the
same deterministic rules the Codebuff version used), and heatmap ranking.
"""

import os
import re
from typing import Any

from pydantic import ValidationError

from .schemas import (
    CheckReports,
    DiffFunction,
    DiffResult,
    HeatmapResult,
    RepoFileRisk,
    RepoHeatmapResult,
    VerdictResult,
)

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
# Used when the primary model hammers into 503/429 on the shared free tier.
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]

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
    import json
    import time

    from google.genai import types

    # The flash aliases occasionally return 503 UNAVAILABLE / 429 quota errors
    # on the shared free tier. Retry with backoff, then fall back to the lite
    # alias (separate rate pool, usually quieter).
    models_to_try = [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]
    last_error: Exception | None = None
    for model in models_to_try:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.1,
                    ),
                )
                text = resp.text or ""
                return json.loads(text)
            except Exception as e:  # noqa: BLE001 - retried/fallback on purpose
                msg = str(e)
                last_error = e
                transient = (
                    "503" in msg
                    or "UNAVAILABLE" in msg
                    or "429" in msg
                    or "RESOURCE_EXHAUSTED" in msg
                )
                if transient:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise  # non-transient (bad key, bad schema, ...): surface it
            break
    raise last_error or RuntimeError("Gemini call failed for unknown reasons")


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


def _verdict_fields() -> dict:
    return {
        "name": {"type": "string"},
        "verdict": {"type": "string", "enum": ["Safe", "Risky", "Needs Review"]},
        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "reason": {"type": "string"},
    }


def merge_diff(items: list[dict], files: list[str]) -> "DiffResult":
    """Verdicts for the changed functions in the working tree.

    items: [{name, file, line, reports: CheckReports}, ...]
    """
    blocks = []
    for it in items:
        r = it["reports"]
        blocks.append(f"FUNCTION: {it['name']} ({it['file']}:{it['line']})\nHISTORY:\n{r.history}\nDOCS:\n{r.docs}\n"
                      f"DEPENDENTS:\n{r.dependents}\nTESTS:\n{r.tests}")
    prompt = (
        "You are the merger of a 'should I touch this' diff review. These are the "
        "functions changed by UNCOMMITTED working-tree edits.\n"
        f"{_VERDICT_RULES}\n\n"
        "For EACH function: give verdict, confidence, and a one-sentence reason "
        "citing its strongest evidence. Rank hottest first: Risky before "
        "Needs Review before Safe.\n\n"
        + "\n\n".join(blocks)
    )
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "functions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {**_verdict_fields(), "file": {"type": "string"},
                                   "line": {"type": "integer"}},
                    "required": ["name", "verdict", "confidence", "reason"],
                },
            },
        },
        "required": ["summary", "functions"],
    }
    client, _ = _client_and_model()
    data = _generate_structured(client, prompt, schema)
    by_name = {it["name"]: it for it in items}
    out: list[DiffFunction] = []
    for f in data.get("functions", []):
        name = f.get("name", "")
        it = by_name.get(name)
        if not it:
            continue
        out.append(DiffFunction(
            name=it["name"], file=it["file"], line=it["line"],
            verdict=f.get("verdict", "Needs Review"),
            confidence=f.get("confidence", "Low"),
            reason=f.get("reason", ""),
        ))
    # Deterministic order + include anything the LLM skipped as Needs Review.
    for it in items:
        if all(o.name != it["name"] for o in out):
            out.append(DiffFunction(
                name=it["name"], file=it["file"], line=it["line"],
                verdict="Needs Review", confidence="Low",
                reason="The merger skipped this function; review the evidence manually.",
            ))
    out.sort(key=lambda d: (_ORDER.get(d.verdict, 1), d.file, d.line))
    return DiffResult(summary=data.get("summary", ""), functions=out, changed_files=files)


def rank_repo(files: dict[str, dict]) -> "RepoHeatmapResult":
    """Repo-wide risk: the LLM summarizes; scores stay deterministic."""
    lines = []
    for path, agg in files.items():
        lines.append(
            f"{path}: {agg['risky']} risky, {agg['review']} review, {agg['safe']} safe "
            f"of {agg['functions']} functions"
        )
    prompt = (
        "You are summarizing a repo-wide risk scan for a 'should I touch this' tool. "
        "In 2-3 sentences name the hottest files and what the pattern suggests. "
        "Do not invent files that are not listed.\n\n" + "\n".join(lines)
    )
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    client, _ = _client_and_model()
    data = _generate_structured(client, prompt, schema)
    out = [
        RepoFileRisk(
            file=path, functions=a["functions"], risky=a["risky"],
            review=a["review"], safe=a["safe"], verdict=a["verdict"], score=a["score"],
        )
        for path, a in files.items()
    ]
    out.sort(key=lambda f: (-f.score, f.file))
    return RepoHeatmapResult(summary=data.get("summary", ""), files=out)


def rule_verdict(reports: CheckReports) -> str:
    """Apply _VERDICT_RULES deterministically in code (no LLM).

    Mirrors the priority the LLM is told to follow: Risky rules first, then
    Safe, else Needs Review. Used for repo-wide aggregation.
    """
    def field(text: str, key: str) -> str:
        for line in text.splitlines():
            if line.startswith(key):
                return line[len(key):].strip()
        return ""

    churn = field(reports.history, "CHURN:")
    suspicious = field(reports.history, "SUSPICIOUS:").lower() == "yes"
    docs_status = field(reports.docs, "STATUS:")
    covered = field(reports.tests, "COVERED:").lower()
    dependents = field(reports.dependents, "DEPENDENT_COUNT:")
    try:
        dependent_count = int(re.search(r"\d+", dependents).group()) if dependents else 0
    except AttributeError:
        dependent_count = 0
    self_contained = field(reports.dependents, "SELF_CONTAINED:").lower() == "yes"
    inconclusive_count = len(reports.inconclusive)

    # RISKY if any of:
    if covered == "no" and dependent_count > 0:
        return "Risky"
    if "HOT" in churn or suspicious:
        return "Risky"
    if docs_status == "WARNED":
        return "Risky"
    # SAFE if any of:
    if docs_status == "DOCUMENTED_CURRENT" and covered in ("yes", "indirectly"):
        return "Safe"
    if self_contained and covered != "no" and docs_status != "WARNED":
        return "Safe"
    if churn.startswith("SINGLE_INTRO") and self_contained:
        return "Safe"
    return "Needs Review"


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
