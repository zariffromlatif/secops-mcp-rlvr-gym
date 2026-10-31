"""Summarize training runs from their samples.jsonl: how each verifier's reward moves over training.

    python -m train.report results/train/v1-run results/train/v3-run [--bucket 10] [--out report.md]

Two "gamed" rates, the answers a weaker verifier pays in full that the full verifier rejects:
    gamed v1  every public test passes (v1 = 1), not solved. The unchanged buggy code is here.
    gamed v2  every public and hidden test passes (v2 = 1), not solved: what only V3's other
              checks (the static gate) catch. If it grows during a V2 run, the policy is learning
              to pass the tests without meeting the task.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(run: Path) -> list[dict]:
    path = run / "samples.jsonl" if run.is_dir() else run
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def gamed(samples: list[dict], key: str) -> float:
    return sum(s[key] == 1 and not s["solved"] for s in samples) / len(samples)


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
            "gamed_v1": gamed(group, "v1"),
            "gamed_v2": gamed(group, "v2"),
        })
    return rows


def per_task(samples: list[dict], last: int) -> list[dict]:
    """Per-task rates over the last `last` steps of a run."""
    end = max(s["step"] for s in samples)
    groups = defaultdict(list)
    for s in samples:
        if s["step"] > end - last:
            groups[s["task"]].append(s)
    return [{"task": task, "n": len(g), "v3": sum(s["v3"] for s in g) / len(g),
             "solved": sum(s["solved"] for s in g) / len(g), "gamed_v1": gamed(g, "v1"), "gamed_v2": gamed(g, "v2")}
            for task, g in sorted(groups.items())]


def render(runs: dict[str, list[dict]], size: int, last: int) -> str:
    out = ["# Training runs", ""]
    for name, samples in runs.items():
        reward = samples[0].get("reward", "?")
        out += [f"## {name} (trained on {reward})", "",
                "| steps | samples | v1 | v2 | v3 | solved | gamed v1 | gamed v2 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in buckets(samples, size):
            out.append(f"| {r['steps']} | {r['n']} | {r['v1']:.3f} | {r['v2']:.3f} | {r['v3']:.3f} "
                       f"| {r['solved']:.1%} | {r['gamed_v1']:.1%} | {r['gamed_v2']:.1%} |")
        out += ["", f"Last {last} steps, per task:", "", "| task | samples | v3 | solved | gamed v1 | gamed v2 |",
                "|---|---:|---:|---:|---:|---:|"]
        for r in per_task(samples, last):
            out.append(f"| {r['task']} | {r['n']} | {r['v3']:.3f} | {r['solved']:.1%} | {r['gamed_v1']:.1%} "
                       f"| {r['gamed_v2']:.1%} |")
        out.append("")
    out.append("gamed v1: all public tests pass, not solved. gamed v2: all tests pass, not solved.")
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
