"""Check every task: gold.patch must be fully solved, noop.patch must score zero on security.

    uv run python runtime/validate_tasks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from score_patch import ROOT, score_patch


def main() -> int:
    failures = 0
    for task_dir in sorted((ROOT / "tasks").glob("*/task.yaml")):
        task_dir = task_dir.parent
        gold = score_patch(task_dir, task_dir / "gold.patch")
        noop = score_patch(task_dir, task_dir / "noop.patch")
        ok = gold.solved and gold.normalized == 1.0 and not noop.solved and noop.security == 0
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'}  {task_dir.name}  "
            f"gold={gold.normalized:.2f}  noop={noop.normalized:.2f}"
        )
        if not ok:
            print(f"      gold notes: {gold.notes}\n      noop notes: {noop.notes}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
