"""Score a folder of model-generated patches in the Docker sandbox and write one CSV.

Expected layout (one subfolder per task id):

    patches/
      invoice_sort_001/
        sample_000.patch
        sample_001.patch
      report_auth_003/
        sample_000.patch

    uv run python runtime/score_batch.py patches/ results.csv --workers 4
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sandbox import sandbox_image
from score_patch import ROOT, score_patch

FIELDS = ["task", "patch", "solved", "normalized", "total", "format", "regression", "security", "static", "notes"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("patches", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    jobs = [
        (ROOT / "tasks" / task_dir.name, patch)
        for task_dir in sorted(p for p in args.patches.iterdir() if p.is_dir())
        for patch in sorted(task_dir.glob("*.patch"))
    ]
    missing = {t.name for t, _ in jobs if not (t / "task.yaml").exists()}
    if missing:
        raise SystemExit(f"unknown task folders: {sorted(missing)}")

    sandbox_image()  # build once before the workers start

    def run(job):
        task_dir, patch = job
        r = score_patch(task_dir, patch, "docker")
        print(f"{task_dir.name}/{patch.name}: {r.normalized:.2f}{' solved' if r.solved else ''}")
        return {
            "task": task_dir.name, "patch": patch.name, "solved": r.solved,
            "normalized": round(r.normalized, 4), "total": round(r.total, 4),
            "format": r.format, "regression": round(r.regression, 4),
            "security": round(r.security, 4), "static": r.static, "notes": "; ".join(r.notes),
        }

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run, jobs))

    with args.out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solved = sum(r["solved"] for r in rows)
    print(f"\n{solved}/{len(rows)} solved -> {args.out}")


if __name__ == "__main__":
    main()
