"""Score a patch against a task.

The patch is applied to a scratch copy holding only what the agent may see.
Hidden tests are copied in only after the patch is applied, then every test
group runs in its own pytest process.

    uv run python runtime/score_patch.py tasks/invoice_sort_001 tasks/invoice_sort_001/gold.patch
    uv run python runtime/score_patch.py --sandbox docker tasks/invoice_sort_001 my.patch

`local` mode imports the app into the test process (fast, for development).
`docker` mode runs it in isolated containers (see sandbox.py) and is the one to trust.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sandbox import parse_junit, run_episode  # noqa: E402
from verifier.gates import RewardBreakdown, score  # noqa: E402

AGENT_VISIBLE = ["app", "tests_public", "seed.sql"]
TMP_ROOT = ROOT / ".tmp"  # keep scratch copies on the repo drive, not %TEMP%


def prepare_workdir(task_dir: Path, workdir: Path) -> None:
    for name in AGENT_VISIBLE:
        src = task_dir / name
        if src.is_dir():
            shutil.copytree(src, workdir / name)
        elif src.exists():
            shutil.copy2(src, workdir / name)


def apply_patch(workdir: Path, patch: Path) -> tuple[bool, list[str]]:
    if not patch.read_text().strip():
        return True, []
    numstat = subprocess.run(
        ["git", "apply", "--numstat", str(patch)], cwd=workdir, capture_output=True, text=True
    )
    if numstat.returncode:
        return False, []
    touched = [line.split("\t")[2] for line in numstat.stdout.splitlines() if line]
    applied = subprocess.run(["git", "apply", str(patch)], cwd=workdir, capture_output=True)
    return applied.returncode == 0, touched


def run_tests(workdir: Path, target: str) -> tuple[int, int]:
    report = workdir / f"report-{abs(hash(target))}.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--timeout=60", f"--junitxml={report}", target],
        cwd=workdir,
        capture_output=True,
    )
    return parse_junit(report)


def run_group(workdir: Path, targets: list[str]) -> tuple[int, int]:
    passed = total = 0
    for target in targets:
        p, t = run_tests(workdir, target)
        passed += p
        total += t
    return passed, total


def read_py(workdir: Path, paths) -> dict[str, str]:
    return {
        str(p).replace("\\", "/"): (workdir / p).read_text()
        for p in paths
        if str(p).endswith(".py") and (workdir / p).exists()
    }


def score_patch(task_dir: Path, patch: Path, sandbox: str = "local") -> RewardBreakdown:
    task_dir, patch = task_dir.resolve(), patch.resolve()
    spec = yaml.safe_load((task_dir / "task.yaml").read_text())["scoring"]
    TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gym-", dir=TMP_ROOT) as tmp:
        workdir = Path(tmp)
        prepare_workdir(task_dir, workdir)

        ok, touched = apply_patch(workdir, patch)
        if not ok:
            r = RewardBreakdown()
            r.format = -0.5
            r.notes.append("patch does not apply")
            return r

        shutil.copytree(task_dir / "hidden", workdir / "hidden")
        app_paths = [p.relative_to(workdir) for p in (workdir / "app").rglob("*.py")]
        if sandbox == "docker":
            n = len(spec["regression"])
            counts = run_episode(workdir, spec["regression"] + spec["security"])
            regression = tuple(map(sum, zip(*counts[:n])))
            security = tuple(map(sum, zip(*counts[n:])))
        else:
            regression = run_group(workdir, spec["regression"])
            security = run_group(workdir, spec["security"])
        return score(
            changed_files=read_py(workdir, touched),
            touched_paths=touched,
            app_files=read_py(workdir, app_paths),
            regression=regression,
            security=security,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--sandbox", choices=["local", "docker"], default="local")
    args = parser.parse_args()
    r = score_patch(args.task_dir, args.patch, args.sandbox)
    print(json.dumps({**asdict(r), "total": r.total, "normalized": round(r.normalized, 3)}, indent=2))


if __name__ == "__main__":
    main()
