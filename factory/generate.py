"""Generate patch tasks from the task families (factory/families.py).

    uv run python -m factory.generate --count 20 --seed 1 --out tasks_generated
    uv run python runtime/validate_tasks.py --tasks-dir tasks_generated --sandbox docker
    uv run python runtime/mutants.py --tasks-dir tasks_generated --check

Generated tasks have the layout of tasks/, plus the generic exploits (edited tests and seed data).
The same --seed always gives the same tasks, so anyone with this code can rebuild a split from its
seed. For a private held-out split, pass a long random --secret (or set GYM_FACTORY_SECRET) and keep
it out of the repository: the secret seeds the generator, and task ids carry only a hash of it.

    uv run python -m factory.generate --count 10 --secret "$(openssl rand -hex 16)" --out tasks_private

Both default output folders are git-ignored. Answer files carry the canary (verifier/canary.py).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import shutil
from pathlib import Path

from factory.common import ROOT, generic_exploits
from factory.families import FAMILIES
from verifier.canary import mark


def generate(family: str, seed: int, index: int, secret: str = "") -> tuple[str, dict[str, str]]:
    if secret:
        tag = hashlib.sha256(f"{secret}:{seed}".encode()).hexdigest()[:8]
        task_id, rng = f"gen_{family}_{tag}_{index:03d}", random.Random(f"{secret}:{family}:{seed}:{index}")
    else:
        task_id, rng = f"gen_{family}_{seed:03d}_{index:03d}", random.Random(f"{family}:{seed}:{index}")
    files = FAMILIES[family](rng, task_id)
    return task_id, {rel: mark(rel, content) for rel, content in {**files, **generic_exploits(files)}.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="tasks per family")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--secret", default=os.environ.get("GYM_FACTORY_SECRET", ""),
                        help="seeds a private split; never commit it")
    parser.add_argument("--families", nargs="*", default=sorted(FAMILIES), choices=sorted(FAMILIES))
    parser.add_argument("--out", type=Path, default=ROOT / "tasks_generated")
    args = parser.parse_args()
    for family in args.families:
        for index in range(args.count):
            task_id, files = generate(family, args.seed, index, args.secret)
            task_dir = args.out / task_id
            shutil.rmtree(task_dir, ignore_errors=True)
            for rel, content in files.items():
                (task_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                (task_dir / rel).write_text(content)
    print(f"{args.count * len(args.families)} tasks -> {args.out}")


if __name__ == "__main__":
    main()
