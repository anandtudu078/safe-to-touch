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
To analyze another codebase, its code must be in the container's `target-repo`
(wired in via `TARGET_REPO_PATH`); the paste-a-GitHub-URL feature is planned next.

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
| `GEMINI_MODEL` | `gemini-2.5-flash` | any free-tier model |
| `TARGET_REPO_PATH` | `./target-repo` | repo under investigation |
| `PORT` | `7860` | HF Spaces expects 7860 |
| `AGENT_TIMEOUT_SECONDS` | `240` | whole-investigation cap (both endpoints) |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Gemini API call cap inside the investigation |

---
# 📁 Project layout
