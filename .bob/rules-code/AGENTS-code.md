# Code mode context — Should I Touch This

Extends AGENTS.md with code-mode specifics.

## File ownership map (what to edit for each type of change)

| Change | Primary file(s) |
|---|---|
| New SSE event type | `backend/app/main.py` + `frontend/app/page.tsx` (handleEvent) |
| New check (5th evidence pillar) | `backend/app/checks.py` + `schemas.py` (CheckReports) + `gemini_client.py` (_findings_prompt) |
| New API endpoint | `backend/app/main.py` |
| Verdict rule change | `backend/app/gemini_client.py` (_VERDICT_RULES) |
| UI layout / styling | `frontend/app/page.tsx` + `frontend/app/globals.css` |
| Pydantic schema change | `backend/app/schemas.py` — then run `node scripts/contract-check.mjs` |

## Coding rules (enforce these on every edit)

- Stream generators (`async def stream()`) must `yield _sse({...})` — never yield raw dicts
- All new check functions must return a string in the KEY: value\n format matching existing checks
- `CheckError` is the only exception type that should bubble to the SSE `error` event
- Pydantic models live in `schemas.py`; do not inline model definitions in `main.py`
- CSS class names for verdicts are `verdict-safe`, `verdict-risky`, `verdict-review` — do not introduce new names

## Validation commands to run after every backend change

```bash
python -m py_compile backend/app/main.py backend/app/checks.py backend/app/schemas.py backend/app/gemini_client.py
node scripts/contract-check.mjs
```

## Validation commands to run after every frontend change

```bash
# from frontend/
npx tsc --noEmit
```
