# Demo Runbook — "Should I Touch This"

A 5–6 minute live demo: paste a suspicious line from a legacy codebase, watch 4
parallel checks run, get one verdict. This runbook covers setup the day before,
a minute-by-minute script, and a fallback plan for every failure mode.

---

## 1. Day-before checklist (do NOT skip)

- [ ] `.env` exists with a working `CODEBUFF_API_KEY`
      (get one at codebuff.com/api-keys; test it once — see smoke test below)
- [ ] Target repo cloned with real git history:
      `git clone <repo-url> target-repo`
      Pick a repo with (a) multi-year history, (b) a README or DECISIONS.md,
      (c) some tests. Good candidates: a mature OSS repo you know well.
- [ ] Pick your demo target **in advance**. Ideal: a function with 3+ commits
      touching it, at least one caller in another file, and a test that covers it.
      Write the exact input string down, e.g.:
      `src/utils/date.ts:120`
- [ ] Run the full boot once and time it (see §2). First `next dev` compile is slow;
      after one boot it's warm.
- [ ] Run all smoke tests and expect all green:
      ```bash
      npm run smoke:agents        # 5 agents load
      npm run smoke:orchestrator  # fan-out/fallback/merge logic
      # with backend running:      npm run smoke:sse
      ```
- [ ] Do **one real end-to-end investigation** the day before, from the browser.
      Confirm you see: 4 checks animate → a verdict card appears.
- [ ] Laptop: plugged in, screen sleep OFF, browser zoom ~125% for the audience,
      a second browser tab open on the target file in GitHub (for context talk).

## 2. Exact boot sequence (run in order, ~2 minutes)

```bash
# Terminal 1 — backend
./.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
# wait for: "Uvicorn running on http://127.0.0.1:8000"

# Terminal 2 — frontend
cd frontend && npm run dev
# wait for: "Ready in" (first compile may take ~30s; pre-warm before the demo)

# Sanity check either terminal or a third one:
curl -s http://127.0.0.1:8000/health
# expect: {"status":"ok","api_key_set":true,"target_repo_exists":true,...}
```

If `api_key_set` is `false` → the backend was started from the wrong directory or
`.env` is missing → fix before going on stage, not during.

## 3. The script (5–6 minutes)

**0:00–0:45 — The pain.** Open the target repo in GitHub. Show the line.
Story: "Nobody knows why this exists. Changing it means 20–30 minutes of
git-archaeology, or changing it blind and praying."

**0:45–1:15 — The tool.** Switch to localhost:3000. One input, one button.
"Paste the line, hit Investigate. That's the whole product."

**1:15–2:30 — The parallel moment (this is the money shot).** Paste the target,
click **Investigate**. Narrate while the 4 rows animate:
"History is running git blame. Docs is reading the README and DECISIONS.md.
Dependents is searching the whole codebase for callers. Tests is checking
coverage — all four at the same time, not one after another."
Point at the dots going amber → green.

**2:30–3:30 — The verdict.** When the card lands, read top-down:
verdict → confidence → the four one-line findings. Say the verdict rules out
loud if asked: risky when untested-and-used or hotfix-churn; safe when
documented-and-tested or fully self-contained; otherwise needs review.

**3:30–4:30 — Second run, opposite verdict (if time).** Have a second target
ready that lands a different verdict (Safe). Shows the tool discriminates,
doesn't just cry wolf.

**4:30–5:30 — Architecture, briefly.** One slide or the README:
Codebuff custom mode (4 subagents + merge rules) → Node runner via SDK →
FastAPI streaming SSE → Next.js page. Emphasize: verdict rules are
deterministic, so the same evidence gives the same verdict.

## 4. Failure modes → fallbacks

| Symptom | Likely cause | Do this |
|---|---|---|
| `api_key_set:false` in /health | .env missing/not loaded | Restart backend from repo root; keep talking (you have ~15s) |
| `target_repo_exists:false` | repo cloned elsewhere | `TARGET_REPO_PATH` in `.env` should point at it |
| Error event: CODEBUFF_API_KEY not set | same as above | Same fix; if unrecoverable → **Fallback A** |
| Stream hangs > 60s | Codebuff API slow/down | **Fallback A**; do not wait on stage past 60s |
| Error event: "timed out after 240s" | same | **Fallback A** |
| Frontend won't load | port conflict / compile error | Open `frontend/.next` warm build? If broken → **Fallback B** |
| Verdict looks wrong/odd | target picked badly | Use your pre-picked backup target from the day-before checklist |

**Fallback A — recorded run.** Record a full successful run (screen capture,
day before). If the live API fails, say: "Rather than fight conference wifi,
here's the exact run we did this morning," play ~60s of it, then continue the
narration live on the code. Record it at the same zoom level you'll present at.

**Fallback B — CLI demo.** The same capability runs in the terminal with zero
web stack:
```bash
codebuff
@Investigate Safety target-repo/src/utils/date.ts:120
```
Show the parallel subagents in the CLI and the verdict card in the output.

**Never do on stage:** fresh `npm install`, first-ever API call, cloning a repo,
or editing the target choice. Everything on stage must have run before.

## 5. After the demo

```bash
# stop servers
kill $(cat /tmp/uvicorn.pid) 2>/dev/null   # or Ctrl+C in each terminal
```
Leave the repo and `.env` intact for follow-up questions at your table.

---

*Verified paths: backend SSE chain, CORS preflight, frontend build, orchestrator
logic (fan-out/fallback/merge) all pass offline smoke tests. The only step that
cannot be rehearsed without credentials is the real API run — do it the day
before, and record it while you're there.*
