"""FastAPI backend for "Should I Touch This" — Gemini edition.

POST /investigate: 4 deterministic checks (git, docs, dependents, tests) run
in a thread pool, then Gemini merges them into one verdict. Streams the same
SSE events as before (check_start / check_finish / result / error), so the
frontend is unchanged.

POST /heatmap: runs the checks for every function in a file and asks Gemini
to rank them hottest-first.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import checks, gemini_client
from .schemas import CheckReports

BACKEND_DIR = Path(__file__).resolve().parent  # backend/app
PROJECT_ROOT = BACKEND_DIR.parents[1]  # repo root

load_dotenv(PROJECT_ROOT / ".env")

AGENT_TIMEOUT_SECONDS = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "240"))
GEMINI_TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "60"))

app = FastAPI(title="Should I Touch This", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:7860"],
    allow_origin_regex=r"https://.*\.hf\.space",
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    target: str = Field(min_length=1, description="'file.ts:120', 'func in file.ts', or a file path")


class HeatmapRequest(BaseModel):
    file: str = Field(min_length=1, description="File path to scan, e.g. 'src/date.ts'")


def _target_repo() -> Path:
    raw = os.environ.get("TARGET_REPO_PATH", "target-repo")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / raw


@app.get("/files")
async def list_files() -> dict:
    """Return all source files tracked in the target repo, grouped by directory."""
    repo = _target_repo()
    if not repo.is_dir():
        return {"files": [], "error": "Target repo not found"}
    try:
        result = await asyncio.to_thread(
            lambda: __import__("subprocess").run(
                ["git", "-C", str(repo), "ls-files"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout
        )
        files = [f for f in result.strip().splitlines() if f]
        return {"files": sorted(files)}
    except Exception as e:  # noqa: BLE001
        return {"files": [], "error": str(e)}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "engine": "gemini",
        "api_key_set": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "target_repo_exists": _target_repo().is_dir(),
        "target_repo_path": str(_target_repo()),
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


CANONICAL_CHECKS = [
    ("history", "History Analyst"),
    ("docs", "Docs Analyst"),
    ("dependents", "Dependents Mapper"),
    ("tests", "Test Coverage Checker"),
]


async def _check_events(reports: CheckReports) -> AsyncIterator[str]:
    """Emit per-check lifecycle events, then run Gemini with the collected evidence."""
    for _, display in CANONICAL_CHECKS:
        yield _sse({"type": "check_start", "agent_id": display, "display_name": display})
    result = await asyncio.wait_for(
        asyncio.to_thread(gemini_client.merge_verdict, reports),
        timeout=GEMINI_TIMEOUT_SECONDS,
    )
    for _, display in CANONICAL_CHECKS:
        yield _sse({"type": "check_finish", "agent_id": display, "display_name": display})
    yield _sse({"type": "result", "mode": "investigate", **result.model_dump()})


@app.post("/investigate")
async def investigate(req: InvestigateRequest) -> StreamingResponse:
    subject = req.target.strip()

    async def stream() -> AsyncIterator[str]:
        try:
            reports = await asyncio.to_thread(checks.collect, subject)
            async for event in _check_events(reports):
                yield event
        except checks.CheckError as e:
            yield _sse({"type": "error", "message": str(e)})
        except TimeoutError:
            yield _sse({"type": "error", "message": f"Investigation timed out after {AGENT_TIMEOUT_SECONDS:.0f}s"})
        except Exception as e:  # noqa: BLE001 - surfaced to the UI on purpose
            yield _sse({"type": "error", "message": gemini_client.friendly_error(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/heatmap")
async def heatmap(req: HeatmapRequest) -> StreamingResponse:
    file = req.file.strip()

    async def stream() -> AsyncIterator[str]:
        try:
            functions = await asyncio.to_thread(checks.list_functions, file)
            if not functions:
                yield _sse(
                    {
                        "type": "result",
                        "mode": "heatmap",
                        "file": file,
                        "functions": [],
                        "summary": "No functions found in that file.",
                    }
                )
                return

            for _, display in CANONICAL_CHECKS:
                yield _sse({"type": "check_start", "agent_id": display, "display_name": display})

            def collect_all() -> dict[str, CheckReports]:
                out: dict[str, CheckReports] = {}
                for f in functions:
                    try:
                        out[f["name"]] = checks.collect(f"{file}:{f['line']}")
                    except checks.CheckError as e:
                        out[f["name"]] = CheckReports(
                            history=f"INCONCLUSIVE: yes\nNOTES: {e}",
                            docs="INCONCLUSIVE: yes",
                            dependents="INCONCLUSIVE: yes",
                            tests="INCONCLUSIVE: yes",
                            inconclusive=["history", "docs", "dependents", "tests"],
                        )
                return out

            reports_by_function = await asyncio.to_thread(collect_all)
            merged = await asyncio.wait_for(
                asyncio.to_thread(gemini_client.rank_heatmap, file, reports_by_function),
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
            for _, display in CANONICAL_CHECKS:
                yield _sse({"type": "check_finish", "agent_id": display, "display_name": display})
            yield _sse({"type": "result", "mode": "heatmap", **merged.model_dump()})
        except checks.CheckError as e:
            yield _sse({"type": "error", "message": str(e)})
        except TimeoutError:
            yield _sse({"type": "error", "message": f"Heatmap timed out after {GEMINI_TIMEOUT_SECONDS:.0f}s"})
        except Exception as e:  # noqa: BLE001 - surfaced to the UI on purpose
            yield _sse({"type": "error", "message": gemini_client.friendly_error(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# /favicon.ico must be registered BEFORE the StaticFiles mount at "/" so it
# is not shadowed when the frontend export is present.
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


# --- Single-container serving -------------------------------------------------
# The exported Next.js app (frontend/out), mounted LAST so it never shadows
# /health, /investigate, /heatmap, or /favicon.ico. Absent locally unless you
# run the export.
FRONTEND_EXPORT = Path(os.environ.get("FRONTEND_EXPORT", str(PROJECT_ROOT / "frontend/out")))
if FRONTEND_EXPORT.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_EXPORT, html=True), name="frontend")
    print(f"[startup] UI mounted from {FRONTEND_EXPORT}", flush=True)
else:
    print(
        f"[startup] UI NOT FOUND at {FRONTEND_EXPORT} - '/' will 404. "
        "Build the frontend (cd frontend && npm run build) or set FRONTEND_EXPORT.",
        flush=True,
    )
    try:
        entries = sorted(p.name for p in PROJECT_ROOT.iterdir())
        print(f"[startup] repo root contains: {entries}", flush=True)
        fe = PROJECT_ROOT / "frontend"
        if fe.is_dir():
            print(f"[startup] frontend/ contains: {sorted(p.name for p in fe.iterdir())}", flush=True)
        else:
            print("[startup] frontend/ directory itself is MISSING", flush=True)
    except Exception as e:  # noqa: BLE001 - diagnostics only
        print(f"[startup] dir listing failed: {e}", flush=True)

    # Self-contained fallback UI baked into the app: the demo always works,
    # even on runtimes that do not hand over every tracked directory.
    from .fallback_ui import FALLBACK_HTML

    @app.get("/", include_in_schema=False)
    async def fallback_index() -> Response:
        return Response(FALLBACK_HTML, media_type="text/html")
