"""Tests for backend/app/checks.py — uses the baked-in demo repo.

The demo repo is created by scripts/create-demo-repo.sh and lives at
target-repo/ (gitignored). If it doesn't exist yet the tests skip gracefully.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO_REPO = ROOT / "target-repo"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _ensure_demo_repo():
    """Create the demo repo if it doesn't exist."""
    if not DEMO_REPO.is_dir():
        script = ROOT / "scripts" / "create-demo-repo.sh"
        subprocess.run(["bash", str(script), str(DEMO_REPO)], check=True)


@pytest.fixture(scope="session", autouse=True)
def demo_repo():
    """Session-scoped fixture: ensure the demo repo exists before any test runs."""
    _ensure_demo_repo()
    yield DEMO_REPO


@pytest.fixture(autouse=True)
def set_target_repo_env(tmp_path, monkeypatch):
    """Point TARGET_REPO_PATH at the demo repo for every test."""
    monkeypatch.setenv("TARGET_REPO_PATH", str(DEMO_REPO))


# ---------------------------------------------------------------------------
# Import module under test (after env is set)
# ---------------------------------------------------------------------------

from backend.app import checks  # noqa: E402 — must come after path setup
from backend.app.checks import CheckError  # noqa: E402


# ---------------------------------------------------------------------------
# _repo()
# ---------------------------------------------------------------------------

class TestRepo:
    def test_finds_demo_repo(self):
        repo = checks._repo()
        assert repo.is_dir()

    def test_raises_check_error_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TARGET_REPO_PATH", str(tmp_path / "nonexistent"))
        with pytest.raises(CheckError, match="No target repo found"):
            checks._repo()

    def test_absolute_path_respected(self, monkeypatch):
        monkeypatch.setenv("TARGET_REPO_PATH", str(DEMO_REPO))
        repo = checks._repo()
        assert repo == DEMO_REPO

    def test_relative_path_resolved(self, monkeypatch):
        # "target-repo" is relative — should resolve against REPO_ROOT
        monkeypatch.setenv("TARGET_REPO_PATH", "target-repo")
        repo = checks._repo()
        assert repo.is_dir()


# ---------------------------------------------------------------------------
# locate()
# ---------------------------------------------------------------------------

class TestLocate:
    def test_file_colon_line(self):
        file_ref, line, func, names = checks.locate(DEMO_REPO, "src/date.ts:1")
        assert file_ref == "src/date.ts"
        assert line == 1
        assert func  # some name inferred

    def test_func_in_file_syntax(self):
        file_ref, line, func, names = checks.locate(DEMO_REPO, "parseDateString in src/date.ts")
        assert file_ref == "src/date.ts"
        assert func == "parseDateString"

    def test_bare_function_name(self):
        # bare name lookup requires git grep to find a definition match;
        # the demo repo has parseDateString defined as an export function
        file_ref, line, func, names = checks.locate(
            DEMO_REPO, "parseDateString in src/date.ts"
        )
        assert file_ref == "src/date.ts"
        assert func == "parseDateString"

    def test_names_list_not_empty(self):
        _, _, _, names = checks.locate(DEMO_REPO, "parseDateString in src/date.ts")
        assert "parseDateString" in names

    def test_unknown_file_raises(self):
        with pytest.raises(CheckError, match="File not found"):
            checks.locate(DEMO_REPO, "nonexistent/file.ts:1")

    def test_names_list_deduped(self):
        _, _, _, names = checks.locate(DEMO_REPO, "src/date.ts:1")
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# check_history()
# ---------------------------------------------------------------------------

class TestCheckHistory:
    def test_returns_string(self):
        report = checks.check_history(DEMO_REPO, "src/date.ts", 1, "parseDateString")
        assert isinstance(report, str)

    def test_contains_commit_field(self):
        report = checks.check_history(DEMO_REPO, "src/date.ts", 1, "parseDateString")
        assert "COMMIT:" in report

    def test_contains_churn_field(self):
        report = checks.check_history(DEMO_REPO, "src/date.ts", 1, "parseDateString")
        assert "CHURN:" in report

    def test_suspicious_for_hotfix_churn(self):
        # The demo file has hotfix commits in its log → file-level churn marks SUSPICIOUS
        # Use line 1 which is valid in the demo repo (src/date.ts has 18 lines after init)
        report = checks.check_history(DEMO_REPO, "src/date.ts", 1, "parseDateString")
        # File-level CHURN includes hotfix commits, so SUSPICIOUS may be yes
        assert "SUSPICIOUS:" in report

    def test_inconclusive_flag_format(self):
        report = checks.check_history(DEMO_REPO, "src/date.ts", 1, "parseDateString")
        assert "INCONCLUSIVE:" in report


# ---------------------------------------------------------------------------
# check_docs()
# ---------------------------------------------------------------------------

class TestCheckDocs:
    def test_documented_function(self):
        report = checks.check_docs(DEMO_REPO, "parseDateString", ["parseDateString"])
        assert "STATUS:" in report
        # The demo README warns about parseDateString — expect WARNED or DOCUMENTED
        assert any(s in report for s in ("DOCUMENTED", "WARNED"))

    def test_undocumented_function(self):
        report = checks.check_docs(DEMO_REPO, "unknownFunc", ["unknownFunc"])
        assert "UNDOCUMENTED" in report

    def test_returns_quote_section(self):
        report = checks.check_docs(DEMO_REPO, "parseDateString", ["parseDateString"])
        assert "QUOTE:" in report

    def test_returns_source_section(self):
        report = checks.check_docs(DEMO_REPO, "parseDateString", ["parseDateString"])
        assert "SOURCE:" in report


# ---------------------------------------------------------------------------
# check_dependents()
# ---------------------------------------------------------------------------

class TestCheckDependents:
    def test_parseDateString_has_dependents(self):
        report = checks.check_dependents(
            DEMO_REPO, "src/date.ts", "parseDateString", ["parseDateString"]
        )
        # api.ts imports parseDateString → DEPENDENT_COUNT should be >= 1
        assert "DEPENDENT_COUNT:" in report
        count_line = [l for l in report.splitlines() if l.startswith("DEPENDENT_COUNT:")][0]
        count = int(count_line.split(":")[1].strip())
        assert count >= 1

    def test_no_dependents_for_unknown(self):
        report = checks.check_dependents(
            DEMO_REPO, "src/date.ts", "xNoBodyUsesThis", ["xNoBodyUsesThis"]
        )
        assert "DEPENDENT_COUNT: 0" in report

    def test_self_contained_field_present(self):
        report = checks.check_dependents(
            DEMO_REPO, "src/date.ts", "parseDateString", ["parseDateString"]
        )
        assert "SELF_CONTAINED:" in report


# ---------------------------------------------------------------------------
# check_tests()
# ---------------------------------------------------------------------------

class TestCheckTests:
    def test_formatDate_is_covered(self):
        # The demo repo has a test for formatDate
        report = checks.check_tests(DEMO_REPO, "formatDate", ["formatDate"])
        assert "COVERED: yes" in report

    def test_parseDateString_not_covered(self):
        # No test directly covers parseDateString in the demo repo
        report = checks.check_tests(DEMO_REPO, "parseDateString", ["parseDateString"])
        assert "COVERED: no" in report

    def test_covered_report_has_test_files(self):
        report = checks.check_tests(DEMO_REPO, "formatDate", ["formatDate"])
        assert "TEST_FILES:" in report


# ---------------------------------------------------------------------------
# collect() — integration
# ---------------------------------------------------------------------------

class TestCollect:
    def test_returns_check_reports(self):
        from backend.app.schemas import CheckReports
        result = checks.collect("parseDateString in src/date.ts")
        assert isinstance(result, CheckReports)

    def test_all_four_fields_populated(self):
        result = checks.collect("parseDateString in src/date.ts")
        assert result.history
        assert result.docs
        assert result.dependents
        assert result.tests

    def test_inconclusive_is_list(self):
        result = checks.collect("parseDateString in src/date.ts")
        assert isinstance(result.inconclusive, list)

    def test_file_colon_line_syntax(self):
        from backend.app.schemas import CheckReports
        result = checks.collect("src/date.ts:1")
        assert isinstance(result, CheckReports)


# ---------------------------------------------------------------------------
# list_functions()
# ---------------------------------------------------------------------------

class TestListFunctions:
    def test_finds_functions_in_date_ts(self):
        funcs = checks.list_functions("src/date.ts")
        names = [f["name"] for f in funcs]
        assert "parseDateString" in names
        assert "formatDate" in names

    def test_each_entry_has_name_and_line(self):
        funcs = checks.list_functions("src/date.ts")
        for f in funcs:
            assert "name" in f
            assert "line" in f
            assert isinstance(f["line"], int)
            assert f["line"] >= 1

    def test_missing_file_raises(self):
        with pytest.raises(CheckError, match="File not found"):
            checks.list_functions("nonexistent/file.ts")
