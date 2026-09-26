"""FastAPI backend for "Should I Touch This".

POST /investigate streams SSE events while the investigate-safety Codebuff
mode runs (4 parallel checks -> verdict merge), then emits a final `result`
event with the structured verdict.

POST /heatmap does the same for the risk-heatmap mode: every function in a
file, checked and ranked hottest-first.
"""

import asyncio
import json
import os
from collections import deque
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent  # backend/app
PROJECT_ROOT = BACKEND_DIR.parents[1]  # repo root (backend/app -> backend -> root)

load_dotenv(PROJECT_ROOT / ".env")

RUNNER = BACKEND_DIR.parent / "runner" / "investigate.mjs"
AGENT_TIMEOUT_SECONDS = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "240"))

app = FastAPI(title="Should I Touch This", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    target: str = Field(
        min_length=1,
        description="File path + line/function (e.g. 'src/utils/date.ts:120') or a code snippet",
    )


class HeatmapRequest(BaseModel):
    file: str = Field(min_length=1, description="File path to scan, e.g. 'src/date.ts'")


def _target_repo() -> Path:
    return PROJECT_ROOT / os.environ.get("TARGET_REPO_PATH", "target-repo")


@app.get("/health")
async def health() -> dict:
    repo = _target_repo()
    return {
        "status": "ok",
        "api_key_set": bool(os.environ.get("CODEBUFF_API_KEY")),
        "target_repo_exists": repo.is_dir(),
        "target_repo_path": str(repo),
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _run_agent(subject_key: str, subject: str, mode: str) -> AsyncIterator[dict]:
    """Spawn the Node runner and yield its NDJSON events as they arrive."""
    try:
        process = await asyncio.create_subprocess_exec(
            "node",
            str(RUNNER),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
    except FileNotFoundError:
        yield {
            "type": "error",
            "message": "Node.js is not available on PATH; cannot run the investigation runner.",
        }
        return
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    async def write_request() -> None:
        payload = json.dumps(
            {
                "mode": mode,
                subject_key: subject,
                "repo_path": os.environ.get("TARGET_REPO_PATH", "target-repo"),
            }
        ).encode()
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()

    stderr_tail: deque[bytes] = deque(maxlen=30)

    async def drain_stderr() -> None:
        async for chunk in process.stderr:
            stderr_tail.append(chunk)

    writer = asyncio.create_task(write_request())
    stderr_task = asyncio.create_task(drain_stderr())
    emitted_error = False

    try:
        async for raw_line in process.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # ignore non-NDJSON noise
            if event.get("type") == "error":
                emitted_error = True
            yield event
        try:
            await writer
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # runner exited before reading the request; its error surfaces below
        returncode = await process.wait()
        if returncode != 0 and not emitted_error:
            yield {
                "type": "error",
                "message": (
                    "investigate runner failed: "
                    + b"".join(stderr_tail).decode(errors="replace").strip()
                    or f"exit code {returncode}"
                ),
            }
    finally:
        if process.returncode is None:
            process.kill()
        stderr_task.cancel()
        try:
            await stderr_task
        except (asyncio.CancelledError, Exception):
            pass


async def _stream_mode_response(
    mode: str, subject_key: str, subject: str
) -> StreamingResponse:
    """Shared SSE response for both modes."""

    async def stream() -> AsyncIterator[str]:
        try:
            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                async for event in _run_agent(subject_key, subject, mode):
                    yield _sse(event)
        except TimeoutError:
            yield _sse(
                {
                    "type": "error",
                    "message": f"Investigation timed out after {AGENT_TIMEOUT_SECONDS:.0f}s",
                }
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _require_target_repo() -> None:
    if not _target_repo().is_dir():
        raise HTTPException(
            status_code=409,
            detail=(
                "No target repo found. Clone the repo you want to investigate "
                "into ./target-repo (or set TARGET_REPO_PATH)."
            ),
        )


@app.post("/investigate")
async def investigate(req: InvestigateRequest) -> StreamingResponse:
    subject = req.target.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="target must not be blank")
    _require_target_repo()
    return await _stream_mode_response("investigate", "target", subject)


@app.post("/heatmap")
async def heatmap(req: HeatmapRequest) -> StreamingResponse:
    subject = req.file.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="file must not be blank")
    _require_target_repo()
    return await _stream_mode_response("heatmap", "file", subject)
