"""Check every task: gold.patch must be fully solved, noop.patch must score zero on security.

    uv run python runtime/validate_tasks.py                      # local, fast
    uv run python runtime/validate_tasks.py --sandbox docker --repeat 3

With --repeat, every patch is scored several times and any score drift fails
the task as flaky.
"""

from __future__ import annotations

import argparse
import sys

from score_patch import ROOT, score_patch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", choices=["local", "docker"], default="local")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    failures = 0
    for spec in sorted((ROOT / "tasks").glob("*/task.yaml")):
        task_dir = spec.parent
        golds = [score_patch(task_dir, task_dir / "gold.patch", args.sandbox) for _ in range(args.repeat)]
        noops = [score_patch(task_dir, task_dir / "noop.patch", args.sandbox) for _ in range(args.repeat)]
        gold, noop = golds[0], noops[0]
        stable = len({g.total for g in golds}) == 1 and len({n.total for n in noops}) == 1
        ok = stable and gold.solved and gold.normalized == 1.0 and not noop.solved and noop.security == 0
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'}  {task_dir.name}  "
            f"gold={gold.normalized:.2f}  noop={noop.normalized:.2f}"
            + ("" if stable else "  FLAKY")
        )
        if not ok:
            print(f"      gold notes: {gold.notes}\n      noop notes: {noop.notes}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
