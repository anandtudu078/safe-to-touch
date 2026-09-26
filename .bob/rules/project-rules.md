# Project rules — Should I Touch This
# Applies to ALL Bob modes (agent, plan, ask, and any custom modes).
# Place cross-cutting standards here; mode-specific guidance goes in rules-{mode}/.

## Secrets & security (non-negotiable)
- NEVER hardcode API keys, tokens, or passwords in any file
- NEVER commit `.env` or `.env.local` files — they are gitignored
- ALL new secrets MUST be added as HF Spaces secrets or via environment variables
- Run `node scripts/check-secrets.mjs` before every commit

## Schema-first contract
- The single source of truth for the API shape is `backend/app/schemas.py`
- ANY change to `VerdictResult`, `HeatmapResult`, `CheckReports`, or `Evidence` MUST be followed immediately by running `node scripts/contract-check.mjs` to verify the frontend still matches
- Do not add fields to the frontend types (`page.tsx`) without first adding them to the pydantic schema

## SSE streaming rule (critical)
- Stream generator functions (`async def stream()`) MUST yield `_sse({...})` formatted strings
- NEVER yield raw Python dicts from a streaming generator — the client will receive binary garbage
- This applies to BOTH the `/investigate` and `/heatmap` endpoints

## Testing requirements
- Every new backend function in `checks.py` or `main.py` MUST have a corresponding test in `tests/`
- Tests MUST pass without a `GEMINI_API_KEY` — mock Gemini calls with `unittest.mock.patch`
- Run the full suite with `python -m pytest tests/ -q` before committing backend changes

## Verdict rules are locked
- The deterministic verdict rules live in `backend/app/gemini_client.py::_VERDICT_RULES`
- Do NOT soften, reorder, or move these rules into free-form LLM instructions
- The model is a structured formatter — the rules are the logic

## Naming conventions
- SSE `display_name` values are a closed set: `History Analyst`, `Docs Analyst`, `Dependents Mapper`, `Test Coverage Checker`
- These strings appear in three places and must match exactly: `CANONICAL_CHECKS` (main.py), `INITIAL_CHECKS` (page.tsx), and the `CHECKS` array in `fallback_ui.py`
- Changing any one requires changing all three

## Commit hygiene
- Every commit message must have a type prefix: `fix:`, `feat:`, `docs:`, `test:`, `chore:`
- Run `node scripts/contract-check.mjs` and `node scripts/check-secrets.mjs` before pushing
