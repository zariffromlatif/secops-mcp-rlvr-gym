"""Report how far the evaluation campaign has got, and whether it is finished.

    python scripts/campaign_status.py .tmp/campaign/state.txt [--days-run N] [--max-days 4]

state.txt has one line per campaign run: "<env> <model> <run-dir>". A task is done for a run
when it has at least one successful episode. Prints a table, then a final line:
    COMPLETE                every task has a successful episode in every run
    STOPPED                 the day limit was reached (provider limits block the rest)
    IN PROGRESS             more days are needed
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "patches": sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.yaml")),
    "workflows": sorted(p.parent.name for p in (ROOT / "workflows").glob("*/task.yaml")),
}


def run_status(env: str, run_dir: Path) -> dict:
    done, errors = set(), {}
    traces = run_dir / "traces.jsonl"
    if traces.exists():
        for line in traces.read_text(encoding="utf-8").splitlines():
            episode = json.loads(line)
            task, trace = episode["task"]["data"]["name"], episode["traces"][0]
            if episode.get("ok") and trace.get("ok"):
                done.add(task)
            else:
                message = ((trace.get("errors") or [{}])[0].get("message") or "")
                errors[task] = ("request too large" if "too large" in message
                                else "daily quota" if "per day" in message else message[:60] or "error")
    # A run covers the tasks it was started with (every task gets an episode, errored or not),
    # so tasks added to the repo later don't count against it.
    expected = sorted(done | set(errors)) or EXPECTED[env]
    return {"done": sorted(done & set(expected)), "expected": expected,
            "missing": [t for t in expected if t not in done],
            "errors": {t: e for t, e in errors.items() if t not in done}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", type=Path)
    parser.add_argument("--days-run", type=int, default=0)
    parser.add_argument("--max-days", type=int, default=4)
    args = parser.parse_args()
    lines = [l.split() for l in args.state.read_text(encoding="utf-8").splitlines() if l.strip()] if args.state.exists() else []
    complete = bool(lines) and len(lines) == 4
    print("| Environment | Model | Done | Missing (last error) |")
    print("|---|---|---|---|")
    for env, model, run_dir in lines:
        s = run_status(env, ROOT / run_dir)
        complete &= not s["missing"]
        missing = ", ".join(f"{t} ({s['errors'].get(t, 'not run yet')})" for t in s["missing"]) or "none"
        print(f"| {env} | {model} | {len(s['done'])}/{len(s['expected'])} | {missing} |")
    verdict = "COMPLETE" if complete else "STOPPED" if args.days_run >= args.max_days else "IN PROGRESS"
    print(f"\n{verdict} (day {args.days_run} of at most {args.max_days})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
