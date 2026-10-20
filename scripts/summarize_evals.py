"""Summarize vf-eval runs into a results table (Markdown + CSV) under results/evals/.

    uv run python scripts/summarize_evals.py .tmp/evals/<run-dir> [<run-dir> ...]

Per task: attempts, solve rate, mean reward, errored attempts, and (for patch tasks)
mean gate scores; plus an overall row. Errored attempts (provider/infra failures) are
reported separately and excluded from the solve-rate denominator.
"""

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "evals"


def load(run_dir: Path):
    for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines():
        episode = json.loads(line)
        trace = episode["traces"][0]
        yield {
            "task": episode["task"]["data"]["name"],
            "ok": bool(episode["ok"] and trace["ok"]),
            "reward": (trace.get("rewards", {}).get("reward") or {}).get("score"),
            "metrics": trace.get("metrics", {}),
            "tokens": episode.get("num_total_tokens") or 0,
        }


def summarize(run_dir: Path) -> None:
    name = run_dir.name
    env, _, rest = name.partition("--")
    model = rest.rsplit("--", 2)[0].replace("--", "/")
    rows, by_task = [], defaultdict(list)
    for ep in load(run_dir):
        by_task[ep["task"]].append(ep)

    def row(task, eps):
        done = [e for e in eps if e["ok"] and e["reward"] is not None]
        solved = [e for e in done if e["metrics"].get("solved") == 1.0]
        gates = {
            k: round(statistics.mean(e["metrics"][k] for e in done), 2) if done else None
            for k in ("gate_regression", "gate_target")
            if any(k in e["metrics"] for e in done)
        }
        return {
            "task": task,
            "attempts": len(eps),
            "errored": len(eps) - len(done),
            "solved": len(solved),
            "solve_rate": round(len(solved) / len(done), 2) if done else None,
            "mean_reward": round(statistics.mean(e["reward"] for e in done), 3) if done else None,
            **gates,
        }

    for task in sorted(by_task):
        rows.append(row(task, by_task[task]))
    rows.append(row("ALL", [e for eps in by_task.values() for e in eps]))

    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"{env}__{model.replace('/', '_')}__{name.rsplit('--', 1)[-1]}"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / f"{stem}.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = [f"# {env} · {model}", "", f"Source run: `{name}`", "",
             "| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)]
    for r in rows:
        lines.append("| " + " | ".join("" if r.get(k) is None else str(r.get(k)) for k in fields) + " |")
    (OUT / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        summarize(Path(arg))
