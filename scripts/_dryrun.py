"""Dry-run integration test: mocks Gemini, exercises the full SSE pipeline."""
import json
import sys

sys.path.insert(0, ".")

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.schemas import Evidence, HeatmapResult, VerdictResult

# -- fake responses ------------------------------------------------------------

FAKE_VERDICT = VerdictResult(
    verdict="Risky",
    confidence="High",
    summary="parseDateString has a hotfix history and is called by src/api.ts — coordinate before touching.",
    history="3 commits including a hotfix; the file has fix-style commit messages.",
    docs="README warns: Coordinate with the platform team before changing.",
    dependents="src/api.ts references parseDateString directly.",
    tests="tests/date.test.ts covers formatDate but NOT parseDateString.",
    evidence=Evidence(
        history="COMMIT: abc 2024-03 Demo - hotfix: strip trailing Z\nCHURN: HOT (3 commits)",
        docs="README.md: Coordinate with the platform team first.",
        dependents="src/api.ts: references parseDateString",
        tests="COVERED: no\nTEST_FILES: tests/date.test.ts",
    ),
    suggestions=["Add a regression test before modifying", "Notify platform team"],
)

FAKE_HEATMAP = HeatmapResult.model_validate(
    {
        "file": "src/date.ts",
        "functions": [
            {
                "name": "parseDateString",
                "line": 1,
                "verdict": "Risky",
                "confidence": "High",
                "reason": "Hotfix history, external dependent, no direct tests.",
            },
            {
                "name": "formatDate",
                "line": 8,
                "verdict": "Safe",
                "confidence": "High",
                "reason": "Stable, tested, self-contained.",
            },
        ],
        "summary": "parseDateString is the hottest function; formatDate is safe.",
    }
)

EXPECTED_INV_SEQ = [
    "check_start", "check_start", "check_start", "check_start",
    "check_finish", "check_finish", "check_finish", "check_finish",
    "result",
]

EXPECTED_HEAT_SEQ = [
    "check_start", "check_start", "check_start", "check_start",
    "check_finish", "check_finish", "check_finish", "check_finish",
    "result",
]

PASS = "PASS"
FAIL = "FAIL"

errors = []


def check(label, condition, detail=""):
    if condition:
        print(f"  [{PASS}]  {label}")
    else:
        msg = f"  [{FAIL}]  {label}" + (f": {detail}" if detail else "")
        print(msg)
        errors.append(label)


with (
    patch("backend.app.gemini_client.merge_verdict", return_value=FAKE_VERDICT),
    patch("backend.app.gemini_client.rank_heatmap", return_value=FAKE_HEATMAP),
):
    from backend.app.main import app

    client = TestClient(app)

    # -- /health ---------------------------------------------------------------
    print("\n-- /health ------------------------------------------------------")
    r = client.get("/health")
    h = r.json()
    check("status 200", r.status_code == 200)
    check("status=ok", h.get("status") == "ok")
    check("engine=gemini", h.get("engine") == "gemini")
    check("api_key_set=true", h.get("api_key_set") is True)
    check("target_repo_exists=true", h.get("target_repo_exists") is True)
    print(f"  target_repo_path: {h.get('target_repo_path')}")

    # -- /files ----------------------------------------------------------------
    print("\n-- /files -------------------------------------------------------")
    r = client.get("/files")
    f = r.json()
    check("status 200", r.status_code == 200)
    check("returns list", isinstance(f.get("files"), list))
    check("contains src/date.ts", "src/date.ts" in f.get("files", []))
    check("contains src/api.ts", "src/api.ts" in f.get("files", []))
    check("contains tests/date.test.ts", "tests/date.test.ts" in f.get("files", []))
    print(f"  files: {f.get('files')}")

    # -- /investigate ----------------------------------------------------------
    print("\n-- /investigate SSE (parseDateString in src/date.ts) -----------")
    with client.stream("POST", "/investigate", json={"target": "parseDateString in src/date.ts"}) as resp:
        events = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]

    seq = [e["type"] for e in events]
    check("event sequence", seq == EXPECTED_INV_SEQ, f"got {seq}")

    starts = [e for e in events if e["type"] == "check_start"]
    finishes = [e for e in events if e["type"] == "check_finish"]
    expected_names = {"History Analyst", "Docs Analyst", "Dependents Mapper", "Test Coverage Checker"}
    check("4 check_start events", len(starts) == 4)
    check("4 check_finish events", len(finishes) == 4)
    check("all display_names present in starts", {e["display_name"] for e in starts} == expected_names)
    check("all display_names present in finishes", {e["display_name"] for e in finishes} == expected_names)

    rv = next((e for e in events if e["type"] == "result"), None)
    check("result event present", rv is not None)
    if rv:
        check("mode=investigate", rv.get("mode") == "investigate")
        check("verdict=Risky", rv.get("verdict") == "Risky")
        check("confidence=High", rv.get("confidence") == "High")
        check("summary non-empty", bool(rv.get("summary")))
        check("history finding present", bool(rv.get("history")))
        check("docs finding present", bool(rv.get("docs")))
        check("dependents finding present", bool(rv.get("dependents")))
        check("tests finding present", bool(rv.get("tests")))
        check("evidence.history present", bool(rv.get("evidence", {}).get("history")))
        check("evidence.docs present", bool(rv.get("evidence", {}).get("docs")))
        check("evidence.dependents present", bool(rv.get("evidence", {}).get("dependents")))
        check("evidence.tests present", bool(rv.get("evidence", {}).get("tests")))
        check("suggestions list present", isinstance(rv.get("suggestions"), list))
        check("suggestions non-empty", len(rv.get("suggestions", [])) > 0)
        print(f"  verdict: {rv['verdict']} | confidence: {rv['confidence']}")
        print(f"  summary: {rv['summary']}")
        print(f"  suggestions: {rv['suggestions']}")

    # -- /investigate — bad input -----------------------------------------------
    print("\n-- /investigate SSE (nonexistent.ts — error path) --------------")
    with client.stream("POST", "/investigate", json={"target": "nonexistent_func_xyz in nonexistent.ts"}) as resp:
        err_events = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    err_ev = next((e for e in err_events if e["type"] == "error"), None)
    check("error event returned for bad target", err_ev is not None)
    if err_ev:
        check("error message non-empty", bool(err_ev.get("message")))
        print(f"  error message: {err_ev['message']}")

    # -- /heatmap --------------------------------------------------------------
    print("\n-- /heatmap SSE (src/date.ts) -----------------------------------")
    with client.stream("POST", "/heatmap", json={"file": "src/date.ts"}) as resp:
        hevents = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]

    hseq = [e["type"] for e in hevents]
    check("event sequence", hseq == EXPECTED_HEAT_SEQ, f"got {hseq}")

    hr = next((e for e in hevents if e["type"] == "result"), None)
    check("result event present", hr is not None)
    if hr:
        check("mode=heatmap", hr.get("mode") == "heatmap")
        check("file=src/date.ts", hr.get("file") == "src/date.ts")
        check("functions is list", isinstance(hr.get("functions"), list))
        check("2 functions returned", len(hr.get("functions", [])) == 2)
        fns = hr.get("functions", [])
        if fns:
            check("hottest function is parseDateString", fns[0]["name"] == "parseDateString")
            check("hottest verdict is Risky", fns[0]["verdict"] == "Risky")
            check("safest function is formatDate", fns[1]["name"] == "formatDate")
            check("safest verdict is Safe", fns[1]["verdict"] == "Safe")
        check("summary non-empty", bool(hr.get("summary")))
        print(f"  file: {hr['file']}")
        for fn in fns:
            print(f"  {fn['verdict']:12s} {fn['name']}:{fn['line']}  ({fn['confidence']}) — {fn['reason']}")

    # -- /heatmap — empty file -------------------------------------------------
    print("\n-- /heatmap SSE (README.md — no functions) ---------------------")
    with client.stream("POST", "/heatmap", json={"file": "README.md"}) as resp:
        mdevents = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    mr = next((e for e in mdevents if e["type"] == "result"), None)
    check("result event returned for no-function file", mr is not None)
    if mr:
        check("functions list empty", mr.get("functions") == [])
        check("summary explains no functions", "No functions" in mr.get("summary", ""))

    # -- /favicon.ico ----------------------------------------------------------
    print("\n-- /favicon.ico -------------------------------------------------")
    r = client.get("/favicon.ico")
    check("returns 204 No Content", r.status_code == 204)
    print(f"  status: {r.status_code}")

# -- summary -------------------------------------------------------------------
print()
if errors:
    print(f"\033[31m{len(errors)} check(s) FAILED:\033[0m")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"\033[32mAll checks passed.\033[0m")
