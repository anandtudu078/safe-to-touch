# Plan mode context — Should I Touch This

Extends AGENTS.md with planning-mode specifics.

## Architecture constraints to respect in any plan

1. **Single container** — FastAPI serves both API and frontend. Avoid plans that require a separate Node server in production.
2. **No database** — The tool is stateless by design. Do not plan persistence features without explicit user request.
3. **Deterministic checks** — Git/grep checks must stay LLM-free. Only the merge/rank step calls Gemini.
4. **SSE contract** — Any new event type must be added to both `CANONICAL_CHECKS`/stream (backend) and `handleEvent` (frontend) atomically.
5. **Verdict values are a closed set** — `"Safe"`, `"Risky"`, `"Needs Review"` only. Plans that add new verdicts must update schemas, CSS, and fallback_ui in lockstep.

## Planned / known next features (do not re-plan these without review)

- Paste-a-GitHub-URL to clone a repo on-the-fly into `target-repo`
- Multiple workers / async check parallelism (currently sequential in `collect()`)
- Confidence score as a numeric float alongside the string label

## Risk areas to flag in any plan touching these

- `checks.py::locate()` — regex-based target resolution is fragile for unusual input formats
- `gemini_client.py::_VERDICT_RULES` — changing rules changes every existing verdict; backward-compat concern
- SSE `display_name` keys — frontend uses these as React keys and CSS class drivers; a rename breaks the UI
