"""Summarize training runs from their samples.jsonl: how each verifier's reward moves over training.

    python -m train.report results/train/v1-run results/train/v3-run [--bucket 10] [--out report.md]

"Gamed" is the share of samples that pass every public test (v1 = 1) but do not solve the task:
the answers a test-only verifier would fully reward that the full verifier rejects. If it grows
while v1 climbs, the policy is learning the tests, not the fix.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(run: Path) -> list[dict]:
    path = run / "samples.jsonl" if run.is_dir() else run
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def buckets(samples: list[dict], size: int) -> list[dict]:
    groups = defaultdict(list)
    for s in samples:
        groups[s["step"] // size * size].append(s)
    rows = []
    for start in sorted(groups):
        group = groups[start]
        n = len(group)
        rows.append({
            "steps": f"{start}-{start + size - 1}",
            "n": n,
            **{k: sum(s[k] for s in group) / n for k in ("v1", "v2", "v3")},
            "solved": sum(s["solved"] for s in group) / n,
            "gamed": sum(s["v1"] == 1 and not s["solved"] for s in group) / n,
        })
    return rows


def per_task(samples: list[dict], last: int) -> list[dict]:
    """Per-task rates over the last `last` steps of a run."""
    end = max(s["step"] for s in samples)
    groups = defaultdict(list)
    for s in samples:
        if s["step"] > end - last:
            groups[s["task"]].append(s)
    return [{"task": task, "n": len(g), "v1": sum(s["v1"] for s in g) / len(g),
             "solved": sum(s["solved"] for s in g) / len(g),
             "gamed": sum(s["v1"] == 1 and not s["solved"] for s in g) / len(g)}
            for task, g in sorted(groups.items())]


def render(runs: dict[str, list[dict]], size: int, last: int) -> str:
    out = ["# Training runs", ""]
    for name, samples in runs.items():
        reward = samples[0].get("reward", "?")
        out += [f"## {name} (trained on {reward})", "",
                "| steps | samples | v1 | v2 | v3 | solved | gamed |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r in buckets(samples, size):
            out.append(f"| {r['steps']} | {r['n']} | {r['v1']:.3f} | {r['v2']:.3f} | {r['v3']:.3f} "
                       f"| {r['solved']:.1%} | {r['gamed']:.1%} |")
        out += ["", f"Last {last} steps, per task:", "", "| task | samples | v1 | solved | gamed |",
                "|---|---:|---:|---:|---:|"]
        for r in per_task(samples, last):
            out.append(f"| {r['task']} | {r['n']} | {r['v1']:.3f} | {r['solved']:.1%} | {r['gamed']:.1%} |")
        out.append("")
    out.append("gamed: v1 = 1 (all public tests pass) but not solved by the full verifier.")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", type=Path, nargs="+", help="run folders (or samples.jsonl files)")
    parser.add_argument("--bucket", type=int, default=10, help="steps per row")
    parser.add_argument("--last", type=int, default=20, help="steps in the per-task table")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    runs = {(r.name if r.is_dir() else r.parent.name): load(r) for r in args.runs}
    text = render(runs, args.bucket, args.last)
    if args.out:
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
