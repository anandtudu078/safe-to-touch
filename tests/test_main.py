"""Tests for FastAPI endpoints in backend/app/main.py.

Uses httpx + TestClient (sync). Gemini calls are monkey-patched out so these
tests run without an API key.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.schemas import (
    CheckReports,
    Evidence,
    HeatmapFunction,
    HeatmapResult,
    VerdictResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient with TARGET_REPO_PATH pointing at the demo repo."""
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    demo = root / "target-repo"

    # Ensure demo repo exists
    if not demo.is_dir():
        import subprocess
        subprocess.run(
            ["bash", str(root / "scripts" / "create-demo-repo.sh"), str(demo)],
            check=True,
        )

    os.environ["TARGET_REPO_PATH"] = str(demo)

    from backend.app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _fake_verdict() -> VerdictResult:
    return VerdictResult(
        verdict="Risky",
        confidence="High",
        summary="Hot churn, no tests.",
        history="3 hotfix commits",
        docs="documented with warning",
        dependents="2 callers",
        tests="no coverage",
        evidence=Evidence(
            history="COMMIT: abc 2024-01-01 Author - hotfix",
            docs="QUOTE: coordinate with platform team",
            dependents="DETAIL: src/api.ts: references parseDateString",
            tests="no test asserts on parseDateString",
        ),
        suggestions=["Add a test before changing this."],
    )


def _fake_heatmap(file: str) -> HeatmapResult:
    return HeatmapResult(
        file=file,
        functions=[
            HeatmapFunction(
                name="parseDateString", line=1,
                verdict="Risky", confidence="High",
                reason="hotfix churn",
            ),
            HeatmapFunction(
                name="formatDate", line=10,
                verdict="Safe", confidence="High",
                reason="well tested",
            ),
        ],
        summary="1 risky function.",
    )


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["engine"] == "gemini"
        assert "target_repo_exists" in body
        assert "api_key_set" in body
        assert "target_repo_path" in body

    def test_target_repo_exists_true(self, client):
        r = client.get("/health")
        assert r.json()["target_repo_exists"] is True


# ---------------------------------------------------------------------------
# /investigate
# ---------------------------------------------------------------------------

class TestInvestigate:
    def _parse_sse(self, text: str) -> list[dict]:
        events = []
        for frame in text.split("\n\n"):
            for line in frame.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    def test_missing_body_returns_422(self, client):
        r = client.post("/investigate", json={})
        assert r.status_code == 422

    def test_empty_target_returns_422(self, client):
        r = client.post("/investigate", json={"target": ""})
        assert r.status_code == 422

    def test_valid_request_streams_sse(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]

    def test_sse_contains_check_start_events(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        events = self._parse_sse(r.text)
        starts = [e for e in events if e["type"] == "check_start"]
        assert len(starts) == 4

    def test_sse_contains_check_finish_events(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        events = self._parse_sse(r.text)
        finishes = [e for e in events if e["type"] == "check_finish"]
        assert len(finishes) == 4

    def test_sse_contains_result_event(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        events = self._parse_sse(r.text)
        results = [e for e in events if e["type"] == "result"]
        assert len(results) == 1
        assert results[0]["verdict"] == "Risky"
        assert results[0]["mode"] == "investigate"

    def test_bad_target_yields_error_event(self, client):
        r = client.post("/investigate", json={"target": "nonexistent/file.ts:1"})
        events = self._parse_sse(r.text)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) >= 1
        assert errors[0]["message"]

    def test_check_start_has_display_name(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        events = self._parse_sse(r.text)
        starts = [e for e in events if e["type"] == "check_start"]
        display_names = {e["display_name"] for e in starts}
        assert "History Analyst" in display_names
        assert "Docs Analyst" in display_names
        assert "Dependents Mapper" in display_names
        assert "Test Coverage Checker" in display_names

    def test_result_contains_evidence(self, client):
        with patch("backend.app.gemini_client.merge_verdict", return_value=_fake_verdict()):
            r = client.post(
                "/investigate",
                json={"target": "parseDateString in src/date.ts"},
            )
        events = self._parse_sse(r.text)
        result = next(e for e in events if e["type"] == "result")
        assert "evidence" in result
        assert "history" in result["evidence"]


# ---------------------------------------------------------------------------
# /heatmap
# ---------------------------------------------------------------------------

class TestHeatmap:
    def _parse_sse(self, text: str) -> list[dict]:
        events = []
        for frame in text.split("\n\n"):
            for line in frame.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    def test_missing_body_returns_422(self, client):
        r = client.post("/heatmap", json={})
        assert r.status_code == 422

    def test_empty_file_returns_422(self, client):
        r = client.post("/heatmap", json={"file": ""})
        assert r.status_code == 422

    def test_valid_request_streams_sse(self, client):
        with patch("backend.app.gemini_client.rank_heatmap",
                   return_value=_fake_heatmap("src/date.ts")):
            r = client.post("/heatmap", json={"file": "src/date.ts"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]

    def test_result_event_has_heatmap_mode(self, client):
        with patch("backend.app.gemini_client.rank_heatmap",
                   return_value=_fake_heatmap("src/date.ts")):
            r = client.post("/heatmap", json={"file": "src/date.ts"})
        events = self._parse_sse(r.text)
        results = [e for e in events if e["type"] == "result"]
        assert results[0]["mode"] == "heatmap"
        assert results[0]["file"] == "src/date.ts"
        assert isinstance(results[0]["functions"], list)

    def test_nonexistent_file_yields_error(self, client):
        r = client.post("/heatmap", json={"file": "nonexistent/file.ts"})
        events = self._parse_sse(r.text)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) >= 1

    def test_check_lifecycle_events_emitted(self, client):
        with patch("backend.app.gemini_client.rank_heatmap",
                   return_value=_fake_heatmap("src/date.ts")):
            r = client.post("/heatmap", json={"file": "src/date.ts"})
        events = self._parse_sse(r.text)
        starts = [e for e in events if e["type"] == "check_start"]
        finishes = [e for e in events if e["type"] == "check_finish"]
        assert len(starts) == 4
        assert len(finishes) == 4

    def test_heatmap_functions_have_required_fields(self, client):
        with patch("backend.app.gemini_client.rank_heatmap",
                   return_value=_fake_heatmap("src/date.ts")):
            r = client.post("/heatmap", json={"file": "src/date.ts"})
        events = self._parse_sse(r.text)
        result = next(e for e in events if e["type"] == "result")
        for fn in result["functions"]:
            assert "name" in fn
            assert "line" in fn
            assert "verdict" in fn
            assert "confidence" in fn
            assert "reason" in fn


# ---------------------------------------------------------------------------
# /favicon.ico
# ---------------------------------------------------------------------------

class TestFavicon:
    def test_returns_no_content_or_not_found(self, client):
        # /favicon.ico returns 204 when the fallback route is active (no frontend/out).
        # When frontend/out is present and mounted as StaticFiles, the static handler
        # either serves a real favicon or 404s — both are acceptable.
        r = client.get("/favicon.ico")
        assert r.status_code in (204, 404)
