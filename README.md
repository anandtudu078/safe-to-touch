---
title: Should I Touch This
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# Should I Touch This (`safe-to-touch`)

Paste a file + line from a legacy codebase. Four deterministic checks run —
**git history, written docs, dependents, test coverage** — and one merge step
produces a single verdict: **Safe / Risky / Needs Review** with a confidence level.

No login, no database, no saved history. One input, one verdict.

**🔗 Live demo:** [huggingface.co/spaces/Anand0303/safe-to-touch](https://huggingface.co/spaces/Anand0303/safe-to-touch)

---

# ✨ Features

| Feature | What it does |
|---|---|
| **Repo connector** | Paste a git URL (auto-cloned) or an absolute local path; everything retargets instantly, no restart |
| **One line** (`/investigate`) | Investigate a single line/function: verdict + confidence + per-check findings with raw-evidence drill-down |
| **Whole file** (`/heatmap`) | Every function in a file ranked hottest-first with a verdict and reason |
| **My changes** (`/diff-investigate`) | Reviews the functions touched by **uncommitted** working-tree edits — "is my change safe?" |
| **Whole repo** (`/repo-heatmap`) | Repo-wide risk treemap: files aggregated by per-function verdicts, hottest first, click to drill in |
| **Relations graph** (`/graph`) | Blast-radius view: what a file depends on, and what depends on it — edges labeled with the connecting symbols, nodes colored by verdict |
| **File editor** (`/file-content`) | Edit any file in the connected repo: save, discard, unsaved indicator |
| **Commit button** (`/file-commit`) | Commit exactly the edited file with your message; badge shows the new HEAD; one click to review the change |
| **Resilient Gemini calls** | Retry with backoff on free-tier 503/429 spikes, automatic fallback to the lite model |
| **Connect-first gate** | Tools stay hidden until a repo is connected; status fetch retries so rebuilds don't look "disconnected" |

---

# 📖 User guide

## How verdicts work

Four deterministic checks run against the connected repo, then explicit
priority rules (applied identically by the LLM merger and by code) produce the
verdict:

| Verdict | When (checked in order) |
|---|---|
| **Risky** | Untested but used elsewhere · hotfix/revert/crash churn or 8+ commits · docs say "do not touch / deprecated / coordinate first" |
| **Safe** | Documented and tested · self-contained (no callers) with some coverage · single-intro and self-contained |
| **Needs Review** | Anything else — evidence is mixed or inconclusive |

A single conventional `fix:` commit is treated as healthy hygiene, not churn.
Each verdict carries a confidence level (High / Medium / Low) and one-line
findings per check, with raw evidence (blame, doc quotes, callers, tests) one
click away.

## 1. One-time setup

- Get a free API key at [aistudio.google.com](https://aistudio.google.com/) and
  put it in `.env` (copy `.env.example`):
  `GEMINI_API_KEY=your-key` — no quotes, no spaces around `=`.
- The built-in synthetic demo repo is baked in and auto-connected, so you can
  try the tool immediately.
- Sanity check: `curl http://127.0.0.1:8000/health` → expect
  `"api_key_set": true` and `"target_repo_exists": true`.

## 2. Start the app

```bash
# Option A — single container (same as the deployed Space)
docker build -t safe-to-touch .
docker run -p 7860:7860 --env GEMINI_API_KEY=YOUR_KEY safe-to-touch
# open http://localhost:7860

# Option B — local dev (two terminals)
python -m uvicorn backend.app.main:app --port 8000   # backend
cd frontend && npm run dev                            # UI on http://localhost:3000
```

## 3. Use the UI — the flow is **connect → edit → investigate**

### Step 1 · Connect a repo (required)

The tools stay hidden until a repo is connected. Click **⚙ Connect repo** and
paste either:

- a **git URL** (`https://github.com/org/repo.git` or ssh) — cloned
  automatically into `target-repo-connected/` (each clone replaces the previous
  one), or
- an **absolute local path** to an existing repo on disk (local runs only —
  the Space container has no paths to your machine).

The badge turns green: `● repo-name · branch · N files`. No restart needed.
This runtime connection overrides `TARGET_REPO_PATH` from `.env`; restarting
the backend reverts to the `.env` default. Use **⚙ Switch repo** any time.

### Step 2 · Edit and commit (optional)

**✏️ Edit files** → pick a file → make your change → **Save** → **✔ Commit**
(you get an inline dialog with a prefilled message). The repo badge shows the
new commit, and **🔍 Review this change** jumps straight to the diff review.

### Step 3 · Investigate

1. **Pick a mode** (tabs): **One line** · **Whole file** · **My changes** ·
   **Whole repo** — the last two need no input, just a click.
2. **Enter the target:**

   | Mode | Accepted input |
   |---|---|
   | One line | `src/utils/date.ts:120`, `parseDateString in src/date.ts`, or a file path |
   | Whole file | `src/utils/date.ts` |
   | My changes / Whole repo | nothing — one click |

   Or click **📂 Browse files** — every row has a **Select** button.
3. **Read the verdict card:** verdict + confidence + one finding per check;
   ▸ expands raw evidence; **Next steps** suggests what to do first.
4. **Relations** appears under the card: three columns — *Depends on · This
   file · Blast radius* — nodes colored by verdict, edges labeled with the
   connecting symbols. Click any node to investigate that file.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` shows `api_key_set: false` | `.env` missing or backend started from the wrong directory — restart from repo root |
| `/health` shows `target_repo_exists: false` | Set `TARGET_REPO_PATH` in `.env`, or use **⚙ Connect repo** in the UI |
| `503 UNAVAILABLE` / high demand | Transient free-tier spike — the backend retries and falls back to the lite model; retry in a minute |
| Model is "no longer available to new users" | `GEMINI_MODEL` pins a retired model — remove the line or use `gemini-flash-latest` |
| `GEMINI_API_KEY` rejected | Check the key; AI Studio keys are unquoted in `.env`. The 4 raw checks run without a key |
| Everything red on my repo | A single `fix:` commit is not churn — red needs hotfix/revert signals, 3+ fix commits, or 8+ commits. Investigate a file to see which rule fired |
| Verdict seems off | Use a more specific target (`file.ts:line` or `func in file.ts`) |
| Space reset to the demo repo after a rebuild | Runtime connections don't survive restarts — reconnect via ⚙ Connect repo |

---

# 🚀 Deployment (Hugging Face Spaces — free, one container)

The app deploys as **one container**: FastAPI serves both the API and the
exported Next.js frontend on a single port, with the demo repo baked in.

## Deploy your own Space

1. Create a free account at huggingface.co → **New Space**
   - SDK: **Gradio → Blank** (the app serves its own FastAPI + UI on 7860)
   - Hardware: **ZeroGPU (Free)** if CPU Basic is unavailable — we use no GPU
   - Public visibility; the API key stays hidden as a Space secret
2. Add the secret: Space → **Settings → Variables and secrets** →
   `GEMINI_API_KEY` = your free key from
   [aistudio.google.com](https://aistudio.google.com/).
   (Secrets are separate from git — updating the repo does **not** update
   secrets, and changing a secret requires a Space restart.)
3. Push this repo as the Space:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/safe-to-touch
   git push space main
   ```
4. Wait for **Building → Running**, then open the Space URL.

The `README.md` frontmatter (title/sdk/app_file) is what the Gradio runtime
reads; `app.py` boots uvicorn on 7860 and bakes the demo repo on first boot.
The Space serves a self-contained fallback UI, so it works even on runtimes
that do not materialize the frontend export.

## Run the container locally

```bash
docker build -t safe-to-touch .
docker run -p 7860:7860 --env GEMINI_API_KEY=YOUR_KEY safe-to-touch
# open http://localhost:7860
```

## Config (env vars)

| Var | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | free key from aistudio.google.com (set as a Space **secret**) |
| `GEMINI_MODEL` | `gemini-flash-latest` | any free-tier model; the alias auto-follows the newest flash |
| `TARGET_REPO_PATH` | `./target-repo` | repo under investigation |
| `PORT` | `7860` | HF Spaces expects 7860 |
| `AGENT_TIMEOUT_SECONDS` | `240` | whole-investigation cap |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Gemini API call cap inside an investigation |
| `FRONTEND_EXPORT` | `./frontend/out` | where FastAPI mounts the exported UI |

---

# 🔌 API reference

All endpoints are same-origin with the UI; SSE responses stream
`data: {json}\n\n` events (`check_start` / `check_finish` / `result` / `error`).

| Method | Endpoint | Body / Query | Returns |
|---|---|---|---|
| GET | `/health` | — | key + repo status |
| GET | `/repo/status` | — | active repo: name, branch, HEAD, file count |
| POST | `/repo/connect` | `{"source": "<git-url or abs path>"}` | clones/validates and activates the repo |
| GET | `/files` | — | tracked files of the active repo |
| GET | `/file-content` | `?file=<repo-relative path>` | file text + line count |
| PATCH | `/file-content` | `{"file", "content"}` | saves the file |
| POST | `/file-commit` | `{"file", "content", "message", "name?", "email?"}` | commits exactly that file |
| POST | `/investigate` | `{"target": "file.ts:120 or func in file.ts"}` | SSE → verdict card |
| POST | `/heatmap` | `{"file": "src/date.ts"}` | SSE → per-function risk ranking |
| POST | `/diff-investigate` | — | SSE → verdicts for uncommitted changes |
| POST | `/repo-heatmap` | — | SSE → repo-wide risk treemap |
| GET | `/graph` | `?file=<path>` | blast-radius nodes + labeled edges, verdict-colored |

Path traversal (e.g. `?file=../../.env`) is rejected on all file endpoints.

---

# 🧪 Testing & validation

```bash
python -m pytest tests/ -q            # 70 backend tests (demo repo, no API key)
node scripts/contract-check.mjs       # pydantic schemas == frontend contract
node scripts/check-secrets.mjs        # no API keys in tracked files
cd frontend && npx tsc --noEmit       # TypeScript check
python -m py_compile backend/app/*.py app.py
```

CI (`.github/workflows/ci.yml`) runs Python tests, the contract check, the
secrets scan, the TypeScript check, and a Docker build + live `/health` check
on every push and PR.

---

# 📁 Project layout

```
safe-to-touch/
├── app.py                     # HF Spaces entrypoint (uvicorn on 7860)
├── backend/app/
│   ├── main.py                # FastAPI: /health, repo+file endpoints, /investigate,
│   │                          #   /heatmap, /diff-investigate, /repo-heatmap, /graph
│   ├── checks.py              # 4 deterministic checks (git CLI + grep), diff
│   │                          #   regions, dependency graph, function listing
│   ├── gemini_client.py       # Gemini merge + ranking, retry/fallback,
│   │                          #   deterministic rule_verdict
│   ├── schemas.py             # Pydantic contracts shared with the frontend
│   └── fallback_ui.py         # Self-contained HTML UI served when the export is absent
├── frontend/
│   ├── app/page.tsx           # Main UI: connector, 4 tabs, editor+commit, relations
│   ├── app/globals.css        # Dark-palette design system
│   └── out/                   # Static export served by FastAPI in one-container mode
├── scripts/
│   ├── create-demo-repo.sh    # Builds the synthetic demo git repo
│   ├── contract-check.mjs     # Schema ↔ frontend contract validation
│   ├── check-secrets.mjs      # Secrets scanner
│   └── sse-smoke.mjs          # Live SSE smoke test (backend must run)
├── docs/DEMO_RUNBOOK.md       # 5–6 minute live demo script + failure playbook
├── target-repo/               # Gitignored — demo repo / repo under investigation
├── Dockerfile                 # Multi-stage: node (frontend build) + python:3.12-slim
└── .github/workflows/ci.yml   # Python tests, Node checks, Docker build smoke
```

## Architecture in one paragraph

The four evidence checks are **deterministic** — plain `git` commands and
greps, no LLM — so the same repo always produces the same raw reports and
nothing breaks without an API key. Gemini is only the **formatter/merger** at
the end: it is instructed to apply the same explicit, ordered verdict rules
that `rule_verdict()` applies in code. FastAPI streams every step over SSE;
the Next.js UI (or the baked-in fallback page) consumes the same event
contract. One container serves everything: API, UI, and the demo repo.

---

*Verdict rules are explicit and ordered — the same evidence always yields the
same verdict.*
