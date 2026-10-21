"""Turn vf-eval run directories into one solutions file for the audit.

Each solution keeps exactly what a verifier needs, and nothing it shouldn't:
- patch tasks: the agent's final app/ files and whether it touched the tests
  (saved in trace.info by the environment from version 0.2.1 on)
- workflows: the agent's tool calls with their results, in order

Episodes that failed for provider reasons (rate limits, oversized requests) are skipped and
counted, because they say nothing about the agent or the verifiers.

    python -m audit.collect .tmp/evals/<run> [<run> ...] --out results/audit/solutions.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _calls(nodes: list[dict]) -> list[dict]:
    calls, by_id = [], {}
    for node in nodes:
        msg = node.get("message") or node
        for call in msg.get("tool_calls") or []:
            fn = call.get("function", call)
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {"_unparsed": args}
            entry = {"tool": fn.get("name"), "args": args}
            calls.append(entry)
            by_id[call.get("id")] = entry
        if msg.get("role") == "tool" and msg.get("tool_call_id") in by_id:
            by_id[msg["tool_call_id"]]["result"] = msg.get("content")
    return calls


def _model(run_name: str) -> str:
    rest = run_name.split("--", 1)[1]
    return rest.rsplit("--", 2)[0].replace("--", "/")


def collect(run_dirs: list[Path]) -> tuple[list[dict], Counter]:
    solutions, skipped = [], Counter()
    for run in run_dirs:
        kind = "workflow" if run.name.startswith("secops_gym_workflows") else "patch"
        attempts = Counter()
        for line in (run / "traces.jsonl").read_text(encoding="utf-8").splitlines():
            episode = json.loads(line)
            trace = episode["traces"][0]
            task = episode["task"]["data"]["name"]
            if not (episode.get("ok") and trace.get("ok")):
                skipped["provider_or_runtime_error"] += 1
                continue
            record = {
                "solution_id": f"{run.name.rsplit('--', 1)[-1]}:{task}:{attempts[task]}",
                "kind": kind, "task": task, "model": _model(run.name), "run": run.name,
            }
            attempts[task] += 1
            if kind == "patch":
                info = (trace.get("info") or {}).get("secops_gym")
                if not info:
                    skipped["no_final_code_in_trace"] += 1  # runs from before version 0.2.1
                    continue
                record["app_files"] = info["final_app_files"]
                record["tests_modified"] = info.get("tests_modified", [])
            else:
                record["calls"] = _calls(trace.get("nodes", []))
            solutions.append(record)
    return solutions, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=Path("results/audit/solutions.jsonl"))
    args = parser.parse_args()
    solutions, skipped = collect(args.runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in solutions), encoding="utf-8")
    print(f"{len(solutions)} solutions -> {args.out}; skipped: {dict(skipped) or 'none'}")


if __name__ == "__main__":
    main()
