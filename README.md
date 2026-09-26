# Should I Touch This (`safe-to-touch`)

Paste a file + line from a legacy codebase. Four subagents investigate in **parallel** —
git history, written docs, dependents, test coverage — and one merge step produces a
single verdict: **Safe / Risky / Needs Review** with a confidence level.

No login, no database, no saved history. One input, one verdict.

## Layout

```
.agents/
  investigate-safety.ts      # Orchestrator: spawns the 4 checks in parallel, merges the verdict
  history-analyst.ts         # git blame / git log — when and why was this introduced
  docs-analyst.ts            # README.md / DECISIONS.md / docs — written intent
  dependents-mapper.ts       # who references or depends on this code
  test-coverage-checker.ts   # does any test exercise this path
target-repo/                 # clone the repo you want to investigate here (gitignored)
backend/
  checks.py                  # 4 deterministic evidence collectors (real git/grep)
  gemini_client.py           # Gemini merge: one-line findings + verdict rules + ranking
  schemas.py                 # output contracts shared with the UI
  main.py                    # FastAPI: POST /investigate + POST /heatmap (SSE)
frontend/                    # Next.js UI: two modes, live checks, cards
scripts/                     # smoke + contract + secret checks
```

**Architecture (v0.3):** the 4 checks are deterministic Python — real `git blame`,
`git log`, `git grep`, and doc/test file scans — so they cannot fail mid-demo.
Gemini (free tier) is used only where language matters: one-line findings, applying
the deterministic verdict rules, and ranking heatmap results. The old Node/Codebuff
bridge was removed.

## Run it now (CLI)

The investigation logic lives in the backend; run the UI:

```bash
cp .env.example .env         # add a free GEMINI_API_KEY from aistudio.google.com
python -m venv .venv
./.venv/Scripts/pip install -r backend/requirements.txt   # Windows Git Bash
# .venv/bin/pip install -r backend/requirements.txt       # macOS/Linux

./.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000

git clone <some-real-repo> target-repo

cd frontend && npm install && npm run dev   # http://localhost:3000
```

## Verdict rules (deterministic, applied by the merge step)

- **Risky** — no test coverage *and* at least one dependent, *or* repeated bugfix/hotfix
  churn on those lines, *or* docs explicitly warn against touching it.
- **Safe** — documented current intent *and* test coverage, *or* fully self-contained code
  (zero dependents, not exported, no test references).
- **Needs Review** — everything else, and any case where the four reports conflict.

Confidence: **High** = all four checks returned concrete evidence · **Medium** = one check
inconclusive · **Low** = two or more inconclusive or the target couldn't be located.

## Backend

FastAPI. Each request runs the 4 deterministic checks (real `git blame`, `git log`,
`git grep`, doc/test scans) in a thread pool, then Gemini merges them into the verdict
and streams the events back to the browser as SSE.

```bash
cp .env.example .env        # add a free GEMINI_API_KEY from aistudio.google.com
python -m venv .venv
./.venv/Scripts/pip install -r backend/requirements.txt   # Windows Git Bash
# .venv/bin/pip install -r backend/requirements.txt       # macOS/Linux

./.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
```

- `GET /health` — reports whether the API key is set and the target repo exists
- `POST /investigate` — body `{ "target": "src/utils/date.ts:120" }`, responds with an
  SSE stream:
  - `check_start` / `check_finish` — one per subagent as the 4 checks run in parallel
  - `result` — the verdict card: `{ verdict, confidence, summary, history, docs,
    dependents, tests, evidence, suggestions }` (evidence holds raw excerpts for
    drill-down)
  - `error` — any failure, as a message
- `POST /heatmap` — body `{ "file": "src/date.ts" }` — checks **every function in the
  file** with the same 4 parallel subagents and returns a ranked list (hottest first):
  `{ file, functions: [{ name, line, verdict, confidence, reason }], summary }`

No auth, no database, no saved history.

## Frontend

One page, two modes:
- **One line** — an input, an "Investigate" button, live status for the 4 parallel
  checks, and a results card with per-check findings. Click ▸ on any finding to
  drill into the raw evidence (actual commits, doc quotes, call sites).
- **Whole file** — paste a file path, get a risk heatmap: every function ranked
  Risky → Needs Review → Safe with its strongest piece of evidence.

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

The frontend talks to the backend at `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`) — see `.env.example`.

## Verifying the setup

```bash
npm run smoke:agents        # all 6 agent definitions load and validate
npm run smoke:orchestrator  # orchestrator fan-out/fallback/merge logic (offline)
npm run smoke:sse           # frontend-style SSE round-trip against a running backend
npm run typecheck           # agent definitions typecheck
cd frontend && npm run typecheck && npm run build
```

## Frontend (next)

Next.js page: one input, one "Investigate" button, live per-check status, one results card.
