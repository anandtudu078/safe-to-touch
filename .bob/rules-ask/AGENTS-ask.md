# Ask mode context — Should I Touch This

Extends AGENTS.md with ask-mode specifics (answering questions about the codebase).

## Quick reference answers

**Q: How does the verdict get decided?**
The 4 checks in `checks.py` collect raw evidence (git, docs, dependents, tests). `gemini_client.merge_verdict()` sends all 4 reports + the explicit `_VERDICT_RULES` to Gemini, which must apply them in order: Risky first, Safe second, Needs Review as fallback.

**Q: What does "inconclusive" mean?**
If a check raises `CheckError` (e.g. git not available, file not found), the check is marked inconclusive. 2+ inconclusive → verdict is always "Needs Review" with Low confidence.

**Q: How does the heatmap work differently from investigate?**
Heatmap calls `list_functions()` to find all functions in a file, runs `collect()` for each one, then calls `gemini_client.rank_heatmap()` which ranks them Risky > Needs Review > Safe in a single Gemini call.

**Q: Why is there a fallback UI?**
Hugging Face Spaces sometimes doesn't hand the container every tracked directory. `fallback_ui.py` bakes a complete single-file HTML app into Python so the demo always works even when `frontend/out` is missing.

**Q: Where is the API contract defined?**
`backend/app/schemas.py` is the single source of truth. `scripts/contract-check.mjs` validates that the frontend renders every required field.
