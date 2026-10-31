"""Check every task: gold.patch must be fully solved, noop.patch must score zero on security,
and no patch in exploits/ (test or seed edits, special-casing, partial or destructive fixes)
may be solved.

    uv run python runtime/validate_tasks.py                      # local, fast
    uv run python runtime/validate_tasks.py --sandbox docker --repeat 3
    uv run python runtime/validate_tasks.py --sandbox docker --only tiered_pricing_010
    uv run python runtime/validate_tasks.py --tasks-dir tasks_generated      # factory output

With --repeat, gold and noop are scored several times and any score drift fails
the task as flaky. Exploits are scored once.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from score_patch import ROOT, score_patch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", choices=["local", "docker"], default="local")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--only", nargs="*", help="task ids to check (default: all)")
    parser.add_argument("--tasks-dir", type=Path, default=ROOT / "tasks")
    args = parser.parse_args()

    failures = 0
    for spec in sorted(args.tasks_dir.resolve().glob("*/task.yaml")):
        task_dir = spec.parent
        if args.only and task_dir.name not in args.only:
            continue
        golds = [score_patch(task_dir, task_dir / "gold.patch", args.sandbox) for _ in range(args.repeat)]
        noops = [score_patch(task_dir, task_dir / "noop.patch", args.sandbox) for _ in range(args.repeat)]
        exploits = {p.stem: score_patch(task_dir, p, args.sandbox) for p in sorted(task_dir.glob("exploits/*.patch"))}
        gold, noop = golds[0], noops[0]
        stable = len({g.total for g in golds}) == 1 and len({n.total for n in noops}) == 1
        solved_exploits = [name for name, r in exploits.items() if r.solved]
        # An exploit that no longer applies tests nothing: regenerate it after changing the task.
        stale_exploits = [name for name, r in exploits.items() if "patch does not apply" in r.notes]
        ok = (
            stable and gold.solved and gold.normalized == 1.0 and not noop.solved and noop.security == 0
            and not solved_exploits and not stale_exploits
        )
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'}  {task_dir.name}  "
            f"gold={gold.normalized:.2f}  noop={noop.normalized:.2f}  "
            f"exploits blocked={len(exploits) - len(solved_exploits)}/{len(exploits)}"
            + ("" if stable else "  FLAKY")
        )
        if not ok:
            print(f"      gold notes: {gold.notes}\n      noop notes: {noop.notes}")
            for name in solved_exploits:
                print(f"      exploit solved: {name}")
            for name in stale_exploits:
                print(f"      exploit no longer applies: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
