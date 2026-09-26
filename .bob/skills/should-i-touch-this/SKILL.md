---
name: should-i-touch-this
description: Expert knowledge for working on the "Should I Touch This" codebase. Covers the SSE contract, verdict rules, evidence check format, pydantic schema, and file ownership map. Activate when adding checks, changing verdict logic, editing SSE events, or modifying the API contract.
---

# Should I Touch This — Skill Instructions

You are working on the **Should I Touch This** (`safe-to-touch`) project — a code-risk analysis tool that runs 4 deterministic git/grep checks and uses Gemini to merge them into a single verdict: **Safe**, **Risky**, or **Needs Review**.

---

## Critical architecture facts

### The SSE event contract (NEVER break this)
All events flow as `data: {JSON}\n\n` over Server-Sent Events.

| Event type | Fields | Direction |
|---|---|---|
| `check_start` | `type`, `agent_id`, `display_name` | backend → frontend |
| `check_finish` | `type`, `agent_id`, `display_name` | backend → frontend |
| `result` | `type`, `mode`, + all VerdictResult/HeatmapResult fields | backend → frontend |
| `error` | `type`, `message` | backend → frontend |

**The `display_name` values are a closed, exact-match set:**
- `History Analyst`
- `Docs Analyst`
- `Dependents Mapper`
- `Test Coverage Checker`

These strings are hard-coded in **3 places** and must stay in sync:
1. `CANONICAL_CHECKS` in `backend/app/main.py`
2. `INITIAL_CHECKS` in `frontend/app/page.tsx`
3. `CHECKS` array in `backend/app/fallback_ui.py`

### Stream generators MUST yield SSE strings
```python
# CORRECT — always wrap with _sse()
yield _sse({"type": "check_start", "display_name": display})

# WRONG — yields a raw dict, client gets garbage
yield {"type": "check_start", "display_name": display}
```

---

## Verdict rules (deterministic, ordered — do NOT change priority)

```
RISKY if any of:
  - Tests: COVERED=no AND Dependents: DEPENDENT_COUNT > 0
  - History: CHURN contains HOT or SUSPICIOUS=yes
  - Docs: STATUS=WARNED

SAFE if any of:
  - Docs: STATUS=DOCUMENTED_CURRENT AND Tests: COVERED=yes/indirectly
  - Dependents: SELF_CONTAINED=yes AND Tests: COVERED≠no AND Docs≠WARNED
  - History: CHURN=SINGLE_INTRO AND Dependents: SELF_CONTAINED=yes

NEEDS REVIEW otherwise; ALWAYS if 2+ reports are INCONCLUSIVE or reports conflict.
```

These rules live in `backend/app/gemini_client.py::_VERDICT_RULES`. Gemini is a structured formatter that applies them — it is NOT a free reasoner for this decision.

---

## Evidence check report format

Every check returns a multi-line string with `KEY: value` lines. The merger reads these verbatim.

### History report keys
```
COMMIT: <hash> <date> <author> - <subject>
WHY: ...
CHURN: SINGLE_INTRO | LIGHT (N commits) | HOT (N commits)
SUSPICIOUS: yes | no
INCONCLUSIVE: yes | no
NOTES: ...
```

### Docs report keys
```
STATUS: UNDOCUMENTED | DOCUMENTED_CURRENT | WARNED
SOURCE: <file(s)>
QUOTE: <verbatim excerpt>
INTENT: ...
STALENESS: unknown
INCONCLUSIVE: yes | no
NOTES: ...
```

### Dependents report keys
```
DEPENDENT_COUNT: <int>
CALL_SITES: <int>
DETAIL: <file: references name>; ...
SELF_CONTAINED: yes | no
BLAST_RADIUS: ...
INCONCLUSIVE: yes | no
NOTES: ...
```

### Tests report keys
```
COVERED: yes | no
TEST_FILES: <comma-separated>
WHAT_ASSERTED: ...
FRAMEWORK: unknown
GAPS: ...
INCONCLUSIVE: yes | no
NOTES: ...
```

---

## File ownership map

| Task | Files to change |
|---|---|
| Add a 5th check | `checks.py` + `schemas.py` (CheckReports) + `gemini_client.py` (_findings_prompt) + `main.py` (CANONICAL_CHECKS) + `page.tsx` (INITIAL_CHECKS) + `fallback_ui.py` (CHECKS) |
| Change verdict rules | `gemini_client.py::_VERDICT_RULES` only |
| Add a new SSE event type | `main.py` (emit it) + `page.tsx` (handleEvent) + `fallback_ui.py` (handle function) |
| Add a new API field | `schemas.py` first → run `node scripts/contract-check.mjs` → update `page.tsx` |
| Fix a check | `checks.py` + add/update test in `tests/test_checks.py` |
| UI change | `frontend/app/page.tsx` + `frontend/app/globals.css` |

---

## Validation commands (run before every commit)

```bash
# Python
python -m py_compile backend/app/main.py backend/app/checks.py backend/app/schemas.py backend/app/gemini_client.py
python -m pytest tests/ -q                      # 70 tests, no API key needed

# Node
node scripts/contract-check.mjs                # schema ↔ frontend contract
node scripts/check-secrets.mjs                 # no API keys committed

# TypeScript (from frontend/)
npx tsc --noEmit
```

---

## What Gemini does (and does NOT do)

| Gemini's job | NOT Gemini's job |
|---|---|
| Convert raw check reports into one-sentence human findings | Running git commands |
| Apply `_VERDICT_RULES` to pick Safe/Risky/Needs Review | Searching the codebase |
| Rank heatmap functions hottest-first | Deciding what evidence to collect |
| Format structured JSON output via `response_schema` | Any non-deterministic reasoning about risk |
