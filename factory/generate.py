"""Generate patch tasks from the task families (factory/families.py).

    uv run python -m factory.generate --count 20 --seed 1 --out tasks_generated
    uv run python runtime/validate_tasks.py --tasks-dir tasks_generated --sandbox docker
    uv run python runtime/mutants.py --tasks-dir tasks_generated --check

Generated tasks have the layout of tasks/, plus the generic exploits (edited tests and seed data).
The same --seed always gives the same tasks. The default output folders are git-ignored: keep a
held-out split out of any public repository, or models trained on public code will have seen it.
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

from factory.common import ROOT, generic_exploits
from factory.families import FAMILIES


def generate(family: str, seed: int, index: int) -> tuple[str, dict[str, str]]:
    task_id = f"gen_{family}_{seed:03d}_{index:03d}"
    rng = random.Random(f"{family}:{seed}:{index}")
    files = FAMILIES[family](rng, task_id)
    return task_id, {**files, **generic_exploits(files)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="tasks per family")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--families", nargs="*", default=sorted(FAMILIES), choices=sorted(FAMILIES))
    parser.add_argument("--out", type=Path, default=ROOT / "tasks_generated")
    args = parser.parse_args()
    for family in args.families:
        for index in range(args.count):
            task_id, files = generate(family, args.seed, index)
            task_dir = args.out / task_id
            shutil.rmtree(task_dir, ignore_errors=True)
            for rel, content in files.items():
                (task_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                (task_dir / rel).write_text(content)
    print(f"{args.count * len(args.families)} tasks -> {args.out}")


if __name__ == "__main__":
    main()
