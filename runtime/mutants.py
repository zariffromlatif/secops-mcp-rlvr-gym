"""Mutation testing for patch tasks: how many small wrong variants of the gold fix do the tests catch?

Each mutant is the gold app with one small change: a flipped comparison or arithmetic operator,
an off-by-one constant, min/max or ceil/floor swapped, a different rounding mode, or, inside SQL
strings, a dropped AND condition or a flipped comparison. A mutant is killed when any public or
hidden test fails. Survivors are either equivalent to the gold (harmless) or a gap in the tests:
review them by hand.

    docker compose -f runtime/docker-compose.yml up -d
    uv run python runtime/mutants.py                         # all tasks -> results/mutation/
    uv run python runtime/mutants.py --only late_fees_014 --workers 4
    uv run python runtime/mutants.py --check                 # fail on unreviewed survivors (CI)

Mutants are our own code, not agent code, so tests run in local mode (fast) against one Postgres
database per worker.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from sandbox import parse_junit
from score_patch import ROOT, TMP_ROOT, apply_patch, prepare_workdir

ADMIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://gym:gym@localhost:5433/gym")
OUT = ROOT / "results" / "mutation"

COMPARE_SWAPS = {"<=": "<", "<": "<=", ">=": ">", ">": ">=", "==": "!=", "!=": "=="}
BINOP_SWAPS = {"+": "-", "-": "+", "//": "/", "/": "//", "*": "+"}
NAME_SWAPS = {"min": "max", "max": "min", "ceil": "floor", "floor": "ceil",
              "ROUND_HALF_UP": "ROUND_HALF_EVEN", "any": "all", "all": "any"}
SQL_WORDS = re.compile(r"\b(SELECT|UPDATE|INSERT|DELETE|WHERE)\b")


@dataclass
class Mutant:
    line: int
    kind: str
    before: str
    after: str
    in_fix: bool  # on a line the gold patch changed
    source: str = ""


def _offset(lines: list[str], line: int, col: int) -> int:
    return sum(len(s) for s in lines[: line - 1]) + col


def _gap(src: str, lines: list[str], left: ast.AST, right: ast.AST) -> tuple[int, int]:
    return (_offset(lines, left.end_lineno, left.end_col_offset), _offset(lines, right.lineno, right.col_offset))


def mutants_for(src: str, fix_lines: set[int]) -> list[Mutant]:
    """Every single-point mutant of `src`, as text edits that keep the formatting."""
    lines = src.splitlines(keepends=True)
    out: list[Mutant] = []

    def add(start: int, end: int, new: str, kind: str, line: int) -> None:
        old = src[start:end]
        if old == new:
            return
        out.append(Mutant(line, kind, old.strip(), new.strip(), line in fix_lines, src[:start] + new + src[end:]))

    def swap_in(start: int, end: int, table: dict, kind: str, line: int) -> None:
        segment = src[start:end]
        for old, new in table.items():
            match = re.search(rf"(?<![<>=!/]){re.escape(old)}(?![<>=/])", segment)
            if match:
                add(start + match.start(), start + match.end(), new, kind, line)
                return

    for node in ast.walk(ast.parse(src)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            start, end = _gap(src, lines, node.left, node.comparators[0])
            swap_in(start, end, COMPARE_SWAPS, "comparison", line)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.FloorDiv, ast.Div, ast.Mult)):
            start, end = _gap(src, lines, node.left, node.right)
            swap_in(start, end, BINOP_SWAPS, "arithmetic", line)
        elif isinstance(node, ast.BoolOp) and len(node.values) == 2:
            start, end = _gap(src, lines, node.values[0], node.values[1])
            add(start, end, src[start:end].replace(" and ", " or ") if isinstance(node.op, ast.And)
                else src[start:end].replace(" or ", " and "), "boolean", line)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            start = _offset(lines, node.lineno, node.col_offset)
            add(start, _offset(lines, node.operand.lineno, node.operand.col_offset), "", "negation", line)
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            start = _offset(lines, node.lineno, node.col_offset)
            end = _offset(lines, node.end_lineno, node.end_col_offset)
            add(start, end, str(node.value + 1), "constant", line)
            add(start, end, str(node.value - 1), "constant", line)
        elif isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in NAME_SWAPS:
                end = _offset(lines, node.end_lineno, node.end_col_offset)
                add(end - len(name), end, NAME_SWAPS[name], "name", line)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL_WORDS.search(node.value):
            start = _offset(lines, node.lineno, node.col_offset)
            end = _offset(lines, node.end_lineno, node.end_col_offset)
            segment = src[start:end]
            for m in re.finditer(r" AND [^\"']+?(?=\s+(?:AND|ORDER|GROUP|RETURNING|LIMIT)\b|\s*[\"'])", segment):
                add(start + m.start(), start + m.end(), "", "sql: drop condition", line)
            for m in re.finditer(r"(?<![<>!])(>=|<=|<|>)(?![=>])", segment):
                add(start + m.start(), start + m.end(), COMPARE_SWAPS[m.group(1)], "sql: comparison", line)
            for m in re.finditer(r"\b(DESC|ASC)\b", segment):
                add(start + m.start(), start + m.end(), "ASC" if m.group(1) == "DESC" else "DESC", "sql: order", line)
    unique = {m.source: m for m in out}
    return sorted(unique.values(), key=lambda m: (not m.in_fix, m.line, m.kind))


def fix_lines(patch: Path, rel: str = "app/main.py") -> set[int]:
    """Lines of the patched file that the gold patch added or changed."""
    changed, current, line = set(), None, 0
    for text in patch.read_text().splitlines():
        if text.startswith("+++ "):
            current = text[4:].split("\t")[0].removeprefix("b/")
        elif text.startswith("@@") and current == rel:
            line = int(re.search(r"\+(\d+)", text).group(1))
        elif current == rel and line:
            if text.startswith("+"):
                changed.add(line)
                line += 1
            elif not text.startswith("-"):
                line += 1
    return changed


def run_tests(workdir: Path, targets: list[str], db_url: str) -> bool:
    """True if every test in every target passes."""
    env = {**os.environ, "DATABASE_URL": db_url, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("APP_URL", None)
    for i, target in enumerate(targets):
        report = workdir / f"report-{i}.xml"
        report.unlink(missing_ok=True)
        try:
            # thread timeouts end the test even when a mutant loops forever inside a request
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--timeout=20",
                            "--timeout-method=thread", f"--junitxml={report}", target],
                           cwd=workdir, env=env, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False
        passed, total = parse_junit(report)
        if passed != total:
            return False
    return True


def worker_databases(n: int) -> list[str]:
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    names = [f"gym_mutants_{i}" for i in range(n)]
    with engine.connect() as conn:
        for name in names:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine.dispose()
    return [make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False) for name in names]


def mutate_task(task_dir: Path, db_urls: list[str], limit: int) -> dict:
    task_dir = task_dir.resolve()
    spec = yaml.safe_load((task_dir / "task.yaml").read_text())["scoring"]
    targets = spec["regression"] + (spec.get("security") or spec["target"])
    TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mut-", dir=TMP_ROOT) as tmp:
        base = Path(tmp) / "base"
        base.mkdir()
        prepare_workdir(task_dir, base)
        assert apply_patch(base, task_dir / "gold.patch")[0], "gold patch does not apply"
        shutil.copytree(task_dir / "hidden", base / "hidden")
        gold = (base / "app" / "main.py").read_text()
        if not run_tests(base, targets, db_urls[0]):
            return {"task": task_dir.name, "error": "gold fails its own tests in local mode"}
        mutants = mutants_for(gold, fix_lines(task_dir / "gold.patch"))[:limit]

        free = queue.Queue()
        for url in db_urls:
            free.put(url)

        def run(job):
            i, mutant = job
            work = Path(tmp) / f"m{i}"
            shutil.copytree(base, work)
            (work / "app" / "main.py").write_text(mutant.source)
            db_url = free.get()  # one database per running mutant, so tests never share one
            try:
                killed = not run_tests(work, targets, db_url)
            finally:
                free.put(db_url)
            shutil.rmtree(work, ignore_errors=True)
            return mutant, killed

        with ThreadPoolExecutor(len(db_urls)) as pool:
            results = list(pool.map(run, enumerate(mutants)))
    survivors = [{k: v for k, v in asdict(m).items() if k != "source"} for m, killed in results if not killed]
    in_fix = [(m, k) for m, k in results if m.in_fix]
    return {
        "task": task_dir.name,
        "mutants": len(results),
        "killed": sum(k for _, k in results),
        "fix_mutants": len(in_fix),
        "fix_killed": sum(k for _, k in in_fix),
        "survivors": survivors,
    }


def survivor_key(task: str, s: dict) -> str:
    return f"{task} L{s['line']} {s['before']} -> {s['after']}"


def write_report(rows: list[dict]) -> list[str]:
    """Write README.md and mutants.json; return the survivors nobody has reviewed yet."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutants.json").write_text(json.dumps(rows, indent=2) + "\n")
    reviewed_path = OUT / "equivalent.yaml"
    reviewed = (yaml.safe_load(reviewed_path.read_text()) or {}) if reviewed_path.exists() else {}
    lines = [
        "# Mutation testing",
        "",
        "Each mutant is the gold fix with one small change (`uv run python runtime/mutants.py`). A test",
        "suite that catches more of them leaves less room for a wrong fix to earn full reward. A",
        "surviving mutant is either equivalent to the gold fix (reviewed in `equivalent.yaml`) or a gap",
        "in the tests.",
        "",
        "| Task | Mutants | Killed | Kill rate | In the fixed lines: killed | Unreviewed survivors |",
        "|---|---|---|---|---|---|",
    ]
    unreviewed = []
    for r in rows:
        if "error" in r:
            lines.append(f"| `{r['task']}` | error: {r['error']} | | | | |")
            continue
        open_ = [s for s in r["survivors"] if survivor_key(r["task"], s) not in reviewed]
        unreviewed += [(r["task"], s) for s in open_]
        rate = r["killed"] / r["mutants"] if r["mutants"] else 0
        lines.append(f"| `{r['task']}` | {r['mutants']} | {r['killed']} | {rate:.0%} | "
                     f"{r['fix_killed']}/{r['fix_mutants']} | {len(open_)} |")
    lines += ["", "## Survivors", ""]
    for r in rows:
        for s in r.get("survivors", []):
            reason = reviewed.get(survivor_key(r["task"], s), "**UNREVIEWED**")
            lines.append(f"- `{survivor_key(r['task'], s)}` ({s['kind']}): {reason}")
    if not any(r.get("survivors") for r in rows):
        lines.append("None.")
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    return [survivor_key(task, s) for task, s in unreviewed]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=60, help="mutants per task (fixed lines first)")
    parser.add_argument("--check", action="store_true", help="exit 1 if a survivor is not in equivalent.yaml")
    args = parser.parse_args()
    db_urls = worker_databases(args.workers)
    rows = []
    for spec in sorted((ROOT / "tasks").glob("*/task.yaml")):
        if args.only and spec.parent.name not in args.only:
            continue
        row = mutate_task(spec.parent, db_urls, args.limit)
        rows.append(row)
        if "error" in row:
            print(f"{row['task']}: {row['error']}")
        else:
            print(f"{row['task']}: killed {row['killed']}/{row['mutants']}, fixed lines {row['fix_killed']}/{row['fix_mutants']}")
    if args.only:
        return 0
    unreviewed = write_report(rows)
    for key in unreviewed:
        print(f"UNREVIEWED survivor: {key}")
    errors = [r["task"] for r in rows if "error" in r]
    return 1 if args.check and (unreviewed or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
