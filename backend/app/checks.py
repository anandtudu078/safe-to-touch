"""The 4 evidence checks, now deterministic Python instead of LLM subagents.

Same reports, same sections, same contract the merger expects — but produced
by real git commands and real searches, so live runs cannot go sideways.
"""

import re
import subprocess
from pathlib import Path

from .schemas import CheckReports

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/app -> backend -> root
# Strong churn signals: emergency repairs and rollbacks. A single conventional
# `fix:` commit is healthy hygiene, not churn — it only counts toward HOT when
# it repeats (>= 3).
HOTFIX_RE = re.compile(r"\b(hotfix|revert|crash|workaround|emergency)\b", re.I)
CONVENTIONAL_FIX_RE = re.compile(r"\b(fix|bug|patch)\b", re.I)
TEST_HINTS = ("test", "spec", "tests/")


class CheckError(Exception):
    pass


def _repo() -> Path:
    import os

    raw = os.environ.get("TARGET_REPO_PATH", "target-repo")
    candidate = Path(raw)
    # If the env var is an absolute path use it directly; otherwise treat it as
    # relative to the project root (the default "target-repo" case).
    repo = candidate if candidate.is_absolute() else REPO_ROOT / raw
    if not repo.is_dir():
        raise CheckError(
            "No target repo found. Clone the repo you want to investigate into "
            "./target-repo (or set TARGET_REPO_PATH)."
        )
    return repo


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return out.stdout
    except subprocess.TimeoutExpired as e:
        raise CheckError(f"git {' '.join(args[:2])} timed out") from e
    except subprocess.CalledProcessError as e:
        raise CheckError(f"git {' '.join(args[:2])} failed: {e.stderr.strip()}") from e
    except FileNotFoundError as e:
        raise CheckError("git is not available on PATH") from e


def _read(repo: Path, rel: str) -> str:
    p = repo / rel
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    return ""


def _search(repo: Path, pattern: str, exclude: str | None = None) -> list[tuple[str, str]]:
    """Search tracked text files (git grep), returning (file, line) pairs."""
    args = ["grep", "-nI", pattern, "--"]
    try:
        out = _git(repo, *args)
    except CheckError:
        return []
    hits: list[tuple[str, str]] = []
    for line in out.splitlines():
        path, _, text = line.partition(":")
        if exclude and path == exclude:
            continue
        hits.append((path, text.strip()))
    return hits


# ---------------------------------------------------------------- locate target


def locate(repo: Path, target: str) -> tuple[str, int, str, list[str]]:
    """Resolve the target to (file, line, function_name, all_names).

    Accepts 'file.ts:120', 'funcName in file.ts', 'file.ts', or a bare name.
    """
    target = target.strip()
    func: str | None = None
    file_ref: str | None = None
    line = 1

    m = re.match(r"^(?P<file>[^:\s]+):(?P<line>\d+)$", target)
    if m:
        file_ref, line = m.group("file"), int(m.group("line"))
    else:
        m = re.match(r"^(?P<name>\w+)\s+in\s+(?P<file>\S+)$", target)
        if m:
            func, file_ref = m.group("name"), m.group("file")
        elif ":" in target and Path(repo / target.split(":")[0]).is_file():
            file_ref = target.split(":")[0]
        else:
            # bare identifier: find its definition
            hits = _search(repo, rf"(function\s+{re.escape(target)}|def\s+{re.escape(target)}\b|"
                               rf"const\s+{re.escape(target)}\s*=|class\s+{re.escape(target)}\b)")
            if hits:
                file_ref = hits[0][0]
                func = target
            else:
                file_ref = target
    if not file_ref:
        raise CheckError(f"Could not interpret target: {target}")

    src = _read(repo, file_ref)
    if not src:
        raise CheckError(f"File not found in target repo: {file_ref}")

    lines = src.splitlines()
    if func is None:
        # infer the enclosing function from the line
        for i in range(min(line, len(lines)) - 1, -1, -1):
            fm = re.search(r"(?:function\s+(\w+)|(?:def|const|class)\s+(\w+))", lines[i])
            if fm:
                func = fm.group(1) or fm.group(2)
                line = i + 1
                break
    if not func:
        func = Path(file_ref).stem

    # every identifier defined at/near the target, for docs/dependents search
    names = [func]
    if 0 < line <= len(lines):
        seg = "\n".join(lines[line - 1 : line + 15])
        names += [
            n for tup in re.findall(r"(?:function\s+(\w+)|def\s+(\w+)|const\s+(\w+)\s*=)", seg)
            for n in tup if n
        ]
    seen: set[str] = set()
    names = [n for n in names if n and not (n in seen or seen.add(n))][:5]
    return file_ref, line, func, names


# ------------------------------------------------------------------- 4 checks


def check_history(repo: Path, file_ref: str, line: int, func: str) -> str:
    blame = _git(repo, "blame", "-l", "-w", "-L", f"{line},{line}", "--", file_ref)
    commit = blame.strip().split()[0].lstrip("^") if blame.strip() else ""
    if not commit:
        return "COMMIT: unknown\nWHY: blame returned nothing\nCHURN: unknown\nSUSPICIOUS: no\nINCONCLUSIVE: yes\nNOTES: no blame output"

    introduced = _git(repo, "log", "-1", "--format=%h|%ad|%an|%s", "--date=short", commit)
    h, date, author, subject = (introduced.strip().split("|", 3) + ["", "", ""])[:4]

    log = _git(repo, "log", "--format=%h|%ad|%s", "--date=short", "--", file_ref)
    commits = [c for c in log.strip().splitlines() if c]
    n = len(commits)
    subjects = [c.split("|", 2)[-1] for c in commits]
    strong = [s for s in subjects if HOTFIX_RE.search(s)]
    conventional = [s for s in subjects if CONVENTIONAL_FIX_RE.search(s)]
    # HOT when: emergency signals (hotfix/revert/crash/...), OR heavy churn
    # including repeated conventional fixes (>= 3 fix: commits), OR many commits.
    has_fixup = bool(strong) or len(conventional) >= 3
    hot = n >= 8 or has_fixup
    if n == 1:
        churn = "SINGLE_INTRO"
    elif hot:
        churn = f"HOT ({n} commits)"
    else:
        churn = f"LIGHT ({n} commits)"
    if strong:
        churn += ", messages include hotfix/revert-style commits"
    elif len(conventional) >= 3:
        churn += f", {len(conventional)} fix-style commits (repeated churn)"
    suspicious = "yes" if hot else "no"

    return (
        f"COMMIT: {h} {date} {author} - {subject}\n"
        f"WHY: introduced per commit message: {subject!r}\n"
        f"CHURN: {churn}\n"
        f"SUSPICIOUS: {suspicious}\n"
        f"INCONCLUSIVE: no\n"
        f"NOTES: churn counted over the whole file {file_ref}"
    )


def check_docs(repo: Path, func: str, names: list[str]) -> str:
    doc_files = [
        p for p in Path.rglob(repo, "*")
        if p.is_file() and p.name.lower() in ("readme.md", "decisions.md", "architecture.md", "changelog.md")
        and "node_modules" not in str(p) and ".git" not in str(p)
    ]
    quotes: list[str] = []
    status = "UNDOCUMENTED"
    for df in doc_files:
        text = _read(repo, str(df.relative_to(repo)))
        for para in re.split(r"\n\s*\n", text):
            if any(n in para for n in names):
                rel = str(df.relative_to(repo))
                quotes.append(f"{rel}: {para.strip()[:300]}")
                lowered = para.lower()
                if any(w in lowered for w in ("do not", "don't", "deprecated", "careful", "coordinate", "risky", "legacy")):
                    status = "WARNED"
                elif status == "UNDOCUMENTED":
                    status = "DOCUMENTED_CURRENT"
    if not quotes:
        return (
            "STATUS: UNDOCUMENTED\nSOURCE: none\nQUOTE: none\n"
            f"INTENT: {func} is not documented in the repo docs I searched.\n"
            "STALENESS: unknown\nINCONCLUSIVE: no\nNOTES: no README/DECISIONS match"
        )
    return (
        f"STATUS: {status}\n"
        f"SOURCE: {', '.join(sorted({q.split(':')[0] for q in quotes}))}\n"
        f"QUOTE: {' | '.join(quotes[:3])}\n"
        f"INTENT: documented as seen in the quotes above.\n"
        "STALENESS: unknown\nINCONCLUSIVE: no\nNOTES: quotes are verbatim excerpts"
    )


NON_CODE_SUFFIXES = (".md", ".txt", ".rst", ".json", ".yml", ".yaml", ".lock")


def check_dependents(repo: Path, file_ref: str, func: str, names: list[str]) -> str:
    dependents: set[str] = set()
    details: list[str] = []
    for name in names:
        for path, text in _search(repo, re.escape(name), exclude=file_ref):
            if path in TEST_HINTS or any(h in path for h in TEST_HINTS):
                continue
            if path.lower().endswith(NON_CODE_SUFFIXES):
                continue  # docs mention code; they are not call sites
            if path not in dependents:
                dependents.add(path)
                details.append(f"{path}: references {name}")
    self_contained = "yes" if not dependents else "no"
    return (
        f"DEPENDENT_COUNT: {len(dependents)}\n"
        f"CALL_SITES: {sum(1 for _ in details)}\n"
        f"DETAIL: {'; '.join(details[:5]) if details else 'none found'}\n"
        f"SELF_CONTAINED: {self_contained}\n"
        f"BLAST_RADIUS: {'nothing outside the file references it' if not dependents else f'{len(dependents)} file(s) reference it'}\n"
        "INCONCLUSIVE: no\nNOTES: git-grep based; dynamic dispatch is not traced"
    )


def check_tests(repo: Path, func: str, names: list[str]) -> str:
    hits: list[tuple[str, str]] = []
    for name in names:
        for path, text in _search(repo, re.escape(name)):
            if any(h in path for h in TEST_HINTS):
                hits.append((path, text))
    if not hits:
        return (
            "COVERED: no\nTEST_FILES: none\n"
            f"WHAT_ASSERTED: no test asserts on {func}.\n"
            "FRAMEWORK: unknown\n"
            f"GAPS: everything about {func} is untested.\n"
            "INCONCLUSIVE: no\nNOTES: searched test-named paths only"
        )
    files = sorted({p for p, _ in hits})
    return (
        "COVERED: yes\n"
        f"TEST_FILES: {', '.join(files[:5])}\n"
        f"WHAT_ASSERTED: references to {func} found in tests (assertion-level check needs review).\n"
        "FRAMEWORK: unknown\n"
        "GAPS: reference-level match; verify the assertions pin actual behavior.\n"
        "INCONCLUSIVE: no\nNOTES: git-grep based coverage hint"
    )


def collect(target: str) -> CheckReports:
    """Run all 4 checks; inconclusive items are listed, not raised."""
    repo = _repo()
    file_ref, line, func, names = locate(repo, target)
    inconclusive: list[str] = []
    reports: dict[str, str] = {}
    for name, fn in (
        ("history", lambda: check_history(repo, file_ref, line, func)),
        ("docs", lambda: check_docs(repo, func, names)),
        ("dependents", lambda: check_dependents(repo, file_ref, func, names)),
        ("tests", lambda: check_tests(repo, func, names)),
    ):
        try:
            reports[name] = fn()
        except CheckError as e:
            inconclusive.append(name)
            reports[name] = (
                f"INCONCLUSIVE: yes\nNOTES: check failed - {e}"
            )
    return CheckReports(
        history=reports["history"],
        docs=reports["docs"],
        dependents=reports["dependents"],
        tests=reports["tests"],
        inconclusive=inconclusive,
    )


def list_functions(target_file: str) -> list[dict]:
    """Every function in the file: (name, line) pairs for the heatmap."""
    repo = _repo()
    src = _read(repo, target_file)
    if not src:
        raise CheckError(f"File not found in target repo: {target_file}")
    out = []
    for i, text in enumerate(src.splitlines(), 1):
        m = re.search(r"(?:function\s+(\w+)|(?:export\s+)?(?:async\s+)?def\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\()", text)
        if m:
            name = m.group(1) or m.group(2) or m.group(3)
            if name:
                out.append({"name": name, "line": i})
    return out


# ------------------------------------------------------------- working-tree diff


def _func_header_re() -> re.Pattern[str]:
    return re.compile(
        r"^\+\s*(?:export\s+)?(?:async\s+)?(?:function\s+(?P<js>\w+)"
        r"|(?:def|class)\s+(?P<py>\w+)"
        r"|const\s+(?P<cs>\w+)\s*=\s*(?:async\s*)?\()"
    )


def changed_regions() -> list[dict]:
    """Functions/regions touched by uncommitted changes (staged + unstaged).

    For each changed file, pair removed/added function-header lines in the diff
    so edits inside an existing function resolve to that function's definition
    line in the current working tree, and brand-new functions resolve to their
    own added header. Falls back to reporting the file itself when no function
    header can be resolved.
    """
    repo = _repo()
    status_out = _git(repo, "status", "--porcelain")
    entries = [ln for ln in status_out.splitlines() if ln.strip()]
    if not entries:
        return []

    header_re = _func_header_re()
    regions: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for entry in entries:
        path = entry[3:].strip().strip('"')
        if path.startswith("...") or "=>" in path:
            continue  # rename pairs / non-plain paths
        if any(h in path for h in TEST_HINTS) or path.lower().endswith(NON_CODE_SUFFIXES):
            continue

        diff = _git(repo, "diff", "HEAD", "--", path)
        if not diff.strip():
            continue

        minus: list[str] = []
        plus: list[str] = []
        cur_file_line = 0
        for dline in diff.splitlines():
            if dline.startswith("@@"):
                m = re.search(r"\+(\d+)", dline.split("@@")[1])
                cur_file_line = int(m.group(1)) - 1 if m else 0
                continue
            if dline.startswith("+") and not dline.startswith("+++"):
                cur_file_line += 1
                hm = header_re.match(dline)
                if hm:
                    plus.append(hm.group("js") or hm.group("py") or hm.group("cs") or "")
            elif dline.startswith("-") and not dline.startswith("---"):
                hm = header_re.match(dline)
                if hm:
                    minus.append(hm.group("js") or hm.group("py") or hm.group("cs") or "")

        if not minus and not plus:
            # changed file but no recognizable function headers
            regions.append({"file": path, "name": "(whole file)", "line": 1})
            continue

        added_names = [n for n in plus if n]
        removed_names = [n for n in minus if n]
        # Edit inside an existing function: the name appears on both sides.
        # New function: added but never removed. Reuse current-tree line numbers.
        funcs_in_file = {f["name"]: f["line"] for f in list_functions(path)}
        resolved: set[str] = set()
        for name in added_names:
            if name in removed_names and name in funcs_in_file:
                regions.append({"file": path, "name": name, "line": funcs_in_file[name]})
                resolved.add(name)
            elif name not in removed_names and name in funcs_in_file:
                regions.append({"file": path, "name": name, "line": funcs_in_file[name]})
                resolved.add(name)
        for name in removed_names:
            if name not in resolved and name in funcs_in_file:
                regions.append({"file": path, "name": name, "line": funcs_in_file[name]})
                resolved.add(name)
        if not resolved:
            regions.append({"file": path, "name": "(whole file)", "line": 1})

    unique: list[dict] = []
    for r in regions:
        key = (r["file"], r["name"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ------------------------------------------------------------- dependency graph


def _resolve_import(repo: Path, source_file: str, spec: str) -> str | None:
    """Resolve an import specifier to a tracked repo file, or None."""
    if not spec.startswith("."):
        return None  # bare package imports are external
    base = (Path(source_file).parent / spec).as_posix()
    candidates = [base] + [f"{base}{ext}" for ext in (
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", "/index.ts", "/index.js",
    )]
    for cand in candidates:
        norm = Path(cand).as_posix()
        if (repo / norm).is_file():
            return norm
    return None


def _import_edges(repo: Path, file_ref: str) -> list[str]:
    """Tracked repo files that file_ref imports from."""
    src = _read(repo, file_ref)
    if not src:
        return []
    specs: set[str] = set()
    for m in re.finditer(
        r"import[\s\S]*?from\s*['\"]([^'\"]+)['\"]|import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        r"|require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)|from\s+([\w.]+)\s+import",
        src,
    ):
        spec = next((g for g in m.groups() if g), None)
        if spec:
            specs.add(spec)
    resolved: list[str] = []
    for spec in sorted(specs):
        target = _resolve_import(repo, file_ref, spec)
        if target and target != file_ref:
            resolved.append(target)
    return resolved


def dependency_graph(file_ref: str, names: list[str], max_nodes: int = 24) -> dict:
    """Blast-radius graph centered on file_ref.

    Left column: files file_ref depends on (its imports).
    Right column: files that depend on file_ref (its blast radius).
    Edges carry labels: the symbols connecting the two files.
    """
    repo = _repo()
    src = _read(repo, file_ref)
    if not src:
        raise CheckError(f"File not found in target repo: {file_ref}")

    def _labels_for(hits: list[tuple[str, str]], other: str) -> list[str]:
        out: list[str] = []
        for _path, text in hits:
            for name in names:
                if re.search(rf"\b{re.escape(name)}\b", text):
                    out.append(name)
        return sorted(set(out))[:4]

    # Left: what file_ref depends on
    deps = _import_edges(repo, file_ref)[:8]
    dep_nodes: list[dict] = []
    for d in deps:
        dep_names = [
            m.group(1) or m.group(2)
            for line in _read(repo, d).splitlines()
            for m in [re.search(r"(?:function\s+(\w+)|(?:export\s+)?(?:async\s+)?def\s+(\w+))", line)]
            if m
        ][:6]
        used_here = _labels_for(
            [("", ln) for ln in _read(repo, file_ref).splitlines()], d
        )
        # symbols defined in d and referenced from file_ref
        labels = sorted(set(n for n in dep_names if re.search(rf"\b{re.escape(n)}\b", src)))[:4]
        if not labels:
            labels = used_here[:2] or [Path(d).name]
        dep_nodes.append({"file": d, "labels": labels})

    # Right: what depends on file_ref (reuse grep-based dependents)
    rev_nodes: list[dict] = []
    seen_files: set[str] = set()
    for name in names:
        for path, text in _search(repo, re.escape(name), exclude=file_ref):
            if path in seen_files or path == file_ref:
                continue
            if any(h in path for h in TEST_HINTS) or path.lower().endswith(NON_CODE_SUFFIXES):
                continue
            seen_files.add(path)
            labels = sorted(set(
                n for n in names if re.search(rf"\b{re.escape(n)}\b", text)
            ))[:4] or [name]
            rev_nodes.append({"file": path, "labels": labels})
            if len(rev_nodes) >= 8:
                break
        if len(rev_nodes) >= 8:
            break

    return {
        "center": file_ref,
        "dependencies": dep_nodes,
        "dependents": rev_nodes,
    }
