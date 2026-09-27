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

Paste a file + line from a legacy codebase. Four checks run **in parallel** —
git history, written docs, dependents, test coverage — and one merge step produces a
single verdict: **Safe / Risky / Needs Review** with a confidence level.

No login, no database, no saved history. One input, one verdict.

---
# 📖 User guide

## How it works

Paste a line from a legacy codebase → four deterministic checks run → one merge
step produces a verdict:

| Verdict | When |
|---|---|
| **Safe** | Documented and tested, or fully self-contained (no callers) |
| **Risky** | Untested but used elsewhere, or heavy hotfix churn |
| **Needs Review** | Anything else — evidence is mixed or incomplete |

Each verdict comes with a confidence level and one-line finding per check.
The verdict rules are deterministic: the same evidence always gives the same verdict.

## 1. One-time setup

- Get a free API key at [aistudio.google.com](https://aistudio.google.com/) and
  put it in `.env` (copy `.env.example` as a starting point):
  `GEMINI_API_KEY=your-key` — no quotes, no spaces around `=`.
- The built-in synthetic demo repo is baked in and auto-connected, so you can
  try the tool immediately.
- Sanity check: `curl http://127.0.0.1:8000/health` → expect
  `"api_key_set": true` and `"target_repo_exists": true`.

## 2. Start the app
<arg_value><b88a6f17>```bash
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

The investigate tools stay hidden until a repo is connected — the page shows a
gate message instead. Click **⚙ Connect repo** and paste either:

- a **git URL** (`https://github.com/org/repo.git` or ssh) — it is cloned
  automatically into `target-repo-connected/` (each clone replaces the previous
  one), or
- an **absolute local path** to an existing repo on disk.

The badge turns green: `● repo-name · branch · N files`. No restart needed —
everything (checks, file list, editor) retargets instantly. This runtime
connection overrides `TARGET_REPO_PATH` from `.env`; restarting the backend
reverts to the `.env` default. Use **⚙ Switch repo** any time.

### Step 2 · Edit files (optional)

Click **✏️ Edit files**, pick a file from the sidebar, make your change, and
**Save** — it writes straight back to the connected repo (Discard and an
"unsaved" indicator included). A typical loop: edit the risky code, then
re-investigate to see whether the verdict improves.

### Step 3 · Investigate

1. **Pick a mode** (tabs at the top):
   - **One line** — investigate a single line/function
   - **Whole file** — risk heatmap of every function in a file, ranked hottest-first
2. **Enter the target:**

   | Mode | Accepted input |
   |---|---|
   | One line | `src/utils/date.ts:120`, `parseDateString in src/date.ts`, or a file path |
   | Whole file | `src/utils/date.ts` |

   Or click **📂 Browse files** to search the tracked files of the connected
   repo and pick one (a pick auto-appends `:1` in One line mode).
3. **Click Investigate / Scan file.** Four check rows animate
   pending → running → done: History, Docs, Dependents, Tests.
4. **Read the verdict card:** verdict + confidence + one-line finding per check.
   Click the ▸ chevron next to any finding to expand the raw evidence
   (git blame output, doc excerpts, caller list, test matches).
   The **Next steps** list suggests what to do before touching the code.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` shows `api_key_set: false` | `.env` missing or backend started from the wrong directory — restart from repo root |
| `/health` shows `target_repo_exists: false` | Repo cloned elsewhere — set `TARGET_REPO_PATH` in `.env`, or use **⚙ Connect repo** in the UI |
| Error: `503 UNAVAILABLE` / high demand | Transient free-tier spike — the backend already retries and falls back to the lite model; if it still fails, retry in a minute |
| Error: model is "no longer available to new users" | Your `GEMINI_MODEL` pins a retired model — remove the line or use `gemini-flash-latest` |
| Error mentions GEMINI_API_KEY not set / rejected | Check the key; AI Studio keys are unquoted in `.env`. The 4 raw checks themselves run without a key |
| Verdict seems off | Try a more specific target (`file.ts:line` or `func in file.ts`) |

---
# 🚀 Deployment (Hugging Face Spaces — free, one container)

The app deploys as **one container**: FastAPI serves both the API and the exported
Next.js frontend on a single port, with the demo repo baked in.

## Deploy your own Space

1. Create a free account at huggingface.co → **New Space**
   - SDK: **Gradio → Blank** (the app serves its own FastAPI + UI on 7860)
   - Hardware: **ZeroGPU (Free)** if CPU Basic is unavailable — we use no GPU
   - Public visibility; the API key stays hidden as a Space secret
2. Add the secret: Space → **Settings → Variables and secrets** →
   `GEMINI_API_KEY` = your free key from [aistudio.google.com](https://aistudio.google.com/)
3. Push this repo as the Space:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/safe-to-touch
   git push space main
   ```
4. Wait for **Building → Running**, then open the Space URL.

The `README.md` frontmatter (title/sdk/app_file) is what the Gradio runtime reads;
`app.py` boots uvicorn on 7860 and bakes the demo repo on first run.

The demo repo ships inside the image — the Space is demo-ready the moment it boots.
To analyze another codebase, use **⚙ Connect repo** in the UI (paste a git URL
or a local path) — no redeploy needed.

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
| `AGENT_TIMEOUT_SECONDS` | `240` | whole-investigation cap (both endpoints) |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Gemini API call cap inside the investigation |

---
# 📁 Project layout
