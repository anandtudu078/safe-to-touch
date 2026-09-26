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
backend/                     # Phase 2: FastAPI + POST /investigate
frontend/                    # Phase 2: Next.js UI
```

## Run it now (CLI)

```bash
npm install
git clone <some-real-repo> target-repo
codebuff
```

Then inside Codebuff:

```
@Investigate Safety target-repo/src/utils/date.ts:120
```

or conversationally:

```
@Investigate Safety is parseDateString in target-repo/src/utils/date.ts safe to delete?
```

## Verdict rules (deterministic, applied by the merge step)

- **Risky** — no test coverage *and* at least one dependent, *or* repeated bugfix/hotfix
  churn on those lines, *or* docs explicitly warn against touching it.
- **Safe** — documented current intent *and* test coverage, *or* fully self-contained code
  (zero dependents, not exported, no test references).
- **Needs Review** — everything else, and any case where the four reports conflict.

Confidence: **High** = all four checks returned concrete evidence · **Medium** = one check
inconclusive · **Low** = two or more inconclusive or the target couldn't be located.

## Backend (Phase 2)

```bash
cp .env.example .env   # add CODEBUFF_API_KEY from codebuff.com/api-keys
```

The FastAPI backend runs this same `investigate-safety` mode headlessly via
`@codebuff/sdk` with the working directory pointed at `target-repo/` (configurable via
`TARGET_REPO_PATH`).
