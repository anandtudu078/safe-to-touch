# AGENTS.md — Should I Touch This (`safe-to-touch`)

> Persistent project context for IBM Bob. Re-run `/init` after major structural changes.

## Project purpose
A single-verdict code-risk tool: paste a file + line from a legacy codebase → four
deterministic checks (git history, docs, dependents, tests) run → Gemini merges them
into one verdict: **Safe / Risky / Needs Review** with a confidence level.

Modes: **Investigate** (one line/function) · **Heatmap** (whole file) ·
**Diff review** (uncommitted changes) · **Repo heatmap** (whole-repo treemap) ·
**Relations graph** (blast radius) — plus a repo connector and an in-browser
file editor with single-file commit.

---

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12), SSE streaming |
| AI merge layer | Google Gemini via `google-genai` SDK (`gemini-flash-latest` default) |
| Evidence checks | Deterministic Python — `git` CLI + regex (no LLM in checks) |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, static export → `frontend/out/` |
| Serving | Single container: FastAPI serves API + exported UI (+ baked fallback UI) |
| Deployment | Docker multi-stage build → Hugging Face Spaces (port 7860) |
| Demo repo | Baked-in synthetic legacy repo (`scripts/create-demo-repo.sh`) |

---

## Repository layout

```
safe-to-touch/
├── app.py                    # HF Spaces entrypoint — boots uvicorn on 7860
├── backend/
│   ├── requirements.txt      # installed by Docker build (identical to root requirements.txt)
│   └── app/
│       ├── main.py           # FastAPI: all endpoints (see below), SSE, static/fallback UI mount
│       ├── checks.py         # deterministic evidence checks, diff regions, dep graph, functions
│       ├── gemini_client.py  # Gemini merge/rank + retry/fallback + rule_verdict()
│       ├── schemas.py        # Pydantic contracts shared with the frontend
│       └── fallback_ui.py    # self-contained HTML UI served when frontend/out is absent
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Main UI: repo connector, 4 tabs, editor+commit, relations
│   │   ├── layout.tsx        # Root layout with metadata
│   │   └── globals.css       # Dark-palette design system
│   └── out/                  # Static export (committed build artifact) served by FastAPI
├── scripts/
│   ├── create-demo-repo.sh   # Builds the synthetic demo git repo
│   ├── contract-check.mjs    # Validates pydantic schema == frontend contract
│   ├── check-secrets.mjs     # Fails if tracked files contain API-key-like strings
│   ├── sse-smoke.mjs         # Smoke test: fires a live SSE request
│   └── _dryrun.py            # Mocks Gemini, exercises the full SSE pipeline
├── tests/                    # 70 pytest tests (demo repo, no API key needed)
├── docs/DEMO_RUNBOOK.md      # Step-by-step live demo script + failure playbook
├── .github/workflows/ci.yml  # Python tests, Node checks, Docker build + /health smoke
├── Dockerfile                # Multi-stage: node (frontend build) + python:3.12-slim
├── requirements.txt          # Root-level (HF Spaces pip install)
└── target-repo/              # Gitignored — demo repo / repo under investigation
    target-repo-connected/    # Gitignored — runtime clones from ⚙ Connect repo
```

---

## API surface (all in `backend/app/main.py`)

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/health` | `api_key_set` + `target_repo_exists` |
| GET | `/repo/status` | active repo: name, branch, HEAD, file count |
| POST | `/repo/connect` | clone allowlisted URL scheme or validate absolute local path |
| GET | `/files` | tracked files of the active repo |
| GET / PATCH | `/file-content` | read / save a repo-relative file |
| POST | `/file-commit` | save + commit exactly that file |
| POST | `/investigate` | SSE → verdict card for `file.ts:120` or `func in file.ts` |
| POST | `/heatmap` | SSE → per-function risk ranking of one file |
| POST | `/diff-investigate` | SSE → verdicts for uncommitted working-tree changes |
| POST | `/repo-heatmap` | SSE → repo-wide risk treemap (≤40 code files) |
| GET | `/graph` | blast-radius nodes + labeled edges |
| GET | `/` | StaticFiles mount of `frontend/out` — or fallback UI if absent (mount is last, never shadows API routes) |

---

## Key architectural decisions

### Evidence checks are deterministic (no LLM)
`checks.py` uses only `git` CLI and `re` (regex). Same codebase → same raw reports,
no API key needed to run the checks. Gemini is used only for the final merge/rank.

### Verdict rules are explicit and ordered
`gemini_client.py::_VERDICT_RULES` defines exact priority rules (Risky > Safe > Needs Review).
The LLM is instructed to apply them verbatim — it is a structured formatter, not a free reasoner.
`rule_verdict()` applies the same rules in code (used by `/repo-heatmap`).

### Single-container deployment
FastAPI serves the API and the exported Next.js static files on one port; if
`frontend/out` is missing, `fallback_ui.py` serves a self-contained HTML page so
the demo always works. In local dev the frontend runs on `:3000` and proxies to
the backend on `:8000` via `NEXT_PUBLIC_API_URL`.

### Runtime repo connection
`POST /repo/connect` clones into `target-repo-connected/` (wiping the previous
clone) or validates a local absolute path, then sets `_ACTIVE_REPO_PATH` and
`TARGET_REPO_PATH` in-process — no restart. Reverting to the `.env` default
requires a backend restart. Clone sources are limited to
`http/ https/ git@/ git/ ssh/` schemes with a 120 s timeout.

### Security invariants (do not weaken)
- **Path traversal**: every file endpoint does
  `target.resolve().relative_to(repo.resolve())` and 400s on `ValueError`
  (also defeats symlink escapes).
- **No shell interpolation**: all `git` subprocess calls pass list args,
  never `shell=True`.
- **Secrets**: `.env` is gitignored; `node scripts/check-secrets.mjs` runs in CI
  and must stay clean. Never hardcode API keys.
- File write/commit and repo-connect endpoints are **unauthenticated** by design
  (demo tool) — adding auth is a product decision, not a drive-by change.

### SSE event contract
All events follow: `data: {JSON}\n\n`
Event types: `check_start` | `check_finish` | `result` | `error`
Display names (used as keys in frontend): `History Analyst`, `Docs Analyst`,
`Dependents Mapper`, `Test Coverage Checker` — these must match exactly in
`CANONICAL_CHECKS` (main.py) and `INITIAL_CHECKS` (page.tsx).
`scripts/contract-check.mjs` validates the pydantic ↔ frontend shape.

---

## Development commands

```bash
# Backend (from repo root; demo repo auto-connects)
python -m uvicorn backend.app.main:app --port 8000 --reload

# Frontend (from frontend/)
npm run dev           # dev server on :3000
npm run build         # static export to frontend/out/
npm run typecheck     # tsc --noEmit

# Tests / checks (from repo root)
python -m pytest tests/ -q        # 70 backend tests, no API key needed
node scripts/contract-check.mjs   # schema vs frontend contract
node scripts/check-secrets.mjs    # no API keys in tracked files
node scripts/sse-smoke.mjs        # live SSE end-to-end (backend must be running)
python -m py_compile backend/app/*.py app.py

# Docker
docker build -t safe-to-touch .
docker run -p 7860:7860 --env GEMINI_API_KEY=YOUR_KEY safe-to-touch
```

CI (`.github/workflows/ci.yml`) runs on push/PR to `main`:
python job (pytest + py_compile + contract check) · node job (tsc + secrets scan) ·
docker job (build + live `/health`, pushes only).

---

## Environment variables

| Var | Default | Required | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | — (falls back to `GOOGLE_API_KEY`) | **Yes** for merge step | Free key from aistudio.google.com; raw checks run without it |
| `GEMINI_MODEL` | `gemini-flash-latest` | No | Any free-tier model; alias auto-follows newest flash |
| `TARGET_REPO_PATH` | `target-repo` | No | Repo under investigation; runtime connect overrides it |
| `PORT` | `7860` | No | HF Spaces expects 7860 |
| `AGENT_TIMEOUT_SECONDS` | `240` | No | Overall investigation cap |
| `GEMINI_TIMEOUT_SECONDS` | `60` | No | Gemini API call cap |
| `FRONTEND_EXPORT` | `./frontend/out` | No | Where FastAPI mounts the exported UI |

---

## Testing / validation

- `python -m pytest tests/ -q` — 70 tests across checks, main, schemas (demo repo, no key)
- `node scripts/contract-check.mjs` — zero-dep schema contract check
- `node scripts/check-secrets.mjs` — tracked-files secret scan (also in CI)
- `npx tsc --noEmit` (in `frontend/`) — TypeScript type check
- `python -m py_compile backend/app/*.py app.py` — Python syntax check
- `node scripts/sse-smoke.mjs` — live SSE smoke (backend must be running)
- `python scripts/_dryrun.py` — full SSE pipeline with Gemini mocked

---

## Conventions Bob should follow in this project

- **Backend**: PEP 8, type hints on all functions, `CheckError` for user-facing errors
- **Frontend**: Functional React components, no class components, `useState` for all state
- **SSE**: Never yield raw dicts from stream generators — always use `_sse({...})`
- **Schemas**: All API contracts live in `backend/app/schemas.py`; change there first, then sync frontend
- **Verdict rules**: Do not move deterministic rules into the LLM prompt freeform — keep `_VERDICT_RULES` explicit and ordered
- **File endpoints**: Any new endpoint touching paths must keep the
  `resolve().relative_to()` traversal guard
- **Git calls**: list args only, never `shell=True`
- **Secrets**: Never hardcode API keys; use `.env` (gitignored) or HF Space secrets
- **Editor files**: `.idea/`, `.vscode/` etc. stay out of git (`.idea/` is gitignored)
