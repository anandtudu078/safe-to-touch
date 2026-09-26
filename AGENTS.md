# AGENTS.md — Should I Touch This (`safe-to-touch`)

> Persistent project context for IBM Bob. Re-run `/init` after major structural changes.

## Project purpose
A single-verdict code-risk tool: paste a file + line from a legacy codebase → four
deterministic checks (git history, docs, dependents, tests) run → Gemini merges them
into one verdict: **Safe / Risky / Needs Review** with a confidence level.

Two modes: **Investigate** (one line/function) and **Heatmap** (whole file, all functions ranked).

---

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12), SSE streaming |
| AI merge layer | Google Gemini via `google-genai` SDK (`gemini-2.5-flash` default) |
| Evidence checks | Deterministic Python — `git` CLI + regex (no LLM in checks) |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, static export |
| Deployment | Docker multi-stage build → Hugging Face Spaces (port 7860) |
| Demo repo | Baked-in synthetic legacy repo (`scripts/create-demo-repo.sh`) |

---

## Repository layout

```
safe-to-touch/
├── app.py                    # HF Spaces entrypoint — boots uvicorn on 7860
├── backend/
│   └── app/
│       ├── main.py           # FastAPI app: /health /investigate /heatmap
│       ├── checks.py         # 4 deterministic evidence checks (git/grep)
│       ├── gemini_client.py  # Gemini structured-output layer (merge + heatmap rank)
│       ├── schemas.py        # Pydantic models: VerdictResult, HeatmapResult, CheckReports
│       └── fallback_ui.py    # Self-contained HTML fallback when frontend/out is absent
├── frontend/
│   └── app/
│       ├── page.tsx          # Main UI: investigate + heatmap modes, SSE consumer
│       ├── layout.tsx        # Root layout with metadata
│       └── globals.css       # Dark-palette design system
├── scripts/
│   ├── create-demo-repo.sh   # Builds the synthetic demo git repo
│   ├── contract-check.mjs    # Validates pydantic schema == frontend contract
│   └── sse-smoke.mjs         # Smoke test: fires a live SSE request
├── docs/
│   └── DEMO_RUNBOOK.md       # Step-by-step live demo script + failure playbook
├── Dockerfile                # Multi-stage: node (frontend build) + python:3.12-slim
├── requirements.txt          # Root-level (HF Spaces pip install)
└── target-repo/              # Gitignored — cloned repo under investigation
```

---

## Key architectural decisions

### Evidence checks are deterministic (no LLM)
`checks.py` uses only `git` CLI and `re` (regex). This means:
- The same codebase always produces the same raw reports
- No API key needed to run the checks
- Gemini is used only for the final merge / language step

### Verdict rules are explicit and ordered
`gemini_client.py::_VERDICT_RULES` defines exact priority rules (Risky > Safe > Needs Review).
The LLM is instructed to apply them verbatim — it is a structured formatter, not a free reasoner.

### Single-container deployment
FastAPI serves both the API (`/investigate`, `/heatmap`, `/health`) and the exported
Next.js static files (`/`). In local dev the frontend runs on `:3000` and proxies
to the backend on `:8000` via `NEXT_PUBLIC_API_URL`.

### SSE event contract
All events follow: `data: {JSON}\n\n`
Event types: `check_start` | `check_finish` | `result` | `error`
Display names (used as keys in frontend): `History Analyst`, `Docs Analyst`,
`Dependents Mapper`, `Test Coverage Checker` — these must match exactly in
`CANONICAL_CHECKS` (main.py) and `INITIAL_CHECKS` (page.tsx).

---

## Development commands

```bash
# Backend (from repo root)
python -m uvicorn backend.app.main:app --port 8000 --reload

# Frontend (from frontend/)
npm run dev           # dev server on :3000
npm run build         # static export to frontend/out/
npm run typecheck     # tsc --noEmit

# Smoke tests (from repo root, backend must be running for sse-smoke)
node scripts/contract-check.mjs   # schema vs frontend contract
node scripts/sse-smoke.mjs        # live SSE end-to-end

# Docker
docker build -t safe-to-touch .
docker run -p 7860:7860 --env GEMINI_API_KEY=YOUR_KEY safe-to-touch
```

---

## Environment variables

| Var | Default | Required | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | — | **Yes** | Free key from aistudio.google.com |
| `GEMINI_MODEL` | `gemini-2.5-flash` | No | Any free-tier model |
| `TARGET_REPO_PATH` | `./target-repo` | No | Absolute or relative to project root |
| `PORT` | `7860` | No | HF Spaces expects 7860 |
| `AGENT_TIMEOUT_SECONDS` | `240` | No | Overall investigation/heatmap cap |
| `GEMINI_TIMEOUT_SECONDS` | `60` | No | Gemini API call cap |

---

## Testing / validation

- `node scripts/contract-check.mjs` — zero-dep schema contract check (no API key needed)
- `node scripts/sse-smoke.mjs` — live SSE smoke test (backend must be running)
- `npx tsc --noEmit` (in `frontend/`) — TypeScript type check
- `python -m py_compile backend/app/*.py` — Python syntax check

---

## Conventions Bob should follow in this project

- **Backend**: PEP 8, type hints on all functions, `CheckError` for user-facing errors
- **Frontend**: Functional React components, no class components, `useState` for all state
- **SSE**: Never yield raw dicts from stream generators — always use `_sse({...})`
- **Schemas**: All API contracts live in `backend/app/schemas.py`; change there first, then sync frontend
- **Verdict rules**: Do not move deterministic rules into the LLM prompt freeform — keep `_VERDICT_RULES` explicit and ordered
- **Secrets**: Never hardcode API keys; use `.env` (gitignored) or HF Space secrets
