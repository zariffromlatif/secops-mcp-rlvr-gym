"""Score every collected solution with V1-V4 and write one verdicts table.

    python -m audit.verify results/audit/solutions.jsonl --out results/audit/verdicts.csv
    python -m audit.verify ... --judge-model openai/gpt-oss-20b \
        --judge-base-url https://api.groq.com/openai/v1 --judge-key-var GROQ_API_KEY
    python -m audit.verify ... --v5-model openai/gpt-oss-120b      # V5: a judge that runs the code

Without --judge-model (--v5-model), V4 (V5) is left empty and can be added in a later run (the
judge caches keep earlier answers).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from audit import agentic_judge
from audit.judge import Judge, patch_prompt, workflow_prompt
from audit.rescore import rescore_patch, rescore_workflow

FIELDS = ["solution_id", "kind", "task", "model", "V1", "V2", "V3", "V4", "V4_reason", "V5", "V5_reason", "details"]


def verify(solutions: list[dict], sandbox: str = "docker", judge: Judge | None = None, v5=None) -> list[dict]:
    rows = []
    for s in solutions:
        if s["kind"] == "patch":
            result = rescore_patch(s["task"], s["app_files"], s.get("tests_modified", []), sandbox=sandbox)
            details = {"counts": result["counts"], "notes": result["notes"]}
            prompt = patch_prompt(s["task"], s["app_files"]) if judge else None
        else:
            result = rescore_workflow(s["task"], [{"tool": c["tool"], "args": c["args"]} for c in s["calls"]])
            details = {"goal": result["goal"], "guard": result["guard"]}
            prompt = workflow_prompt(s["task"], s["calls"]) if judge else None
        verdicts = result["verdicts"]
        row = {
            "solution_id": s["solution_id"], "kind": s["kind"], "task": s["task"], "model": s["model"],
            "V1": verdicts["V1"], "V2": verdicts.get("V2", ""), "V3": verdicts["V3"], "V4": "", "V4_reason": "",
            "V5": "", "V5_reason": "",
            "details": json.dumps(details),
        }
        if judge:
            answer = judge.judge(prompt)
            row["V4"] = "" if answer["verdict"] is None else answer["verdict"]
            row["V4_reason"] = answer["reason"]
        if v5:
            answer = v5.judge(s)
            row["V5"] = "" if answer["verdict"] is None else answer["verdict"]
            row["V5_reason"] = answer["reason"]
        rows.append(row)
        print(f"{s['solution_id']}: V1={row['V1']} V2={row['V2']} V3={row['V3']} V4={row['V4']} V5={row['V5']}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("solutions", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results/audit/verdicts.csv"))
    parser.add_argument("--sandbox", choices=["docker", "warm", "local"], default="docker")
    parser.add_argument("--judge-model")
    parser.add_argument("--judge-base-url", default="https://api.groq.com/openai/v1")
    parser.add_argument("--judge-key-var", default="GROQ_API_KEY")
    parser.add_argument("--v5-model", help="model for V5, the judge that runs the code")
    parser.add_argument("--v5-base-url", default="https://api.groq.com/openai/v1")
    parser.add_argument("--v5-key-var", default="GROQ_API_KEY")
    args = parser.parse_args()
    solutions = [json.loads(line) for line in args.solutions.read_text(encoding="utf-8").splitlines() if line.strip()]
    judge = Judge(args.judge_model, args.judge_base_url, args.judge_key_var) if args.judge_model else None
    v5 = agentic_judge.make(args.v5_model, args.v5_base_url, args.v5_key_var) if args.v5_model else None
    rows = verify(solutions, args.sandbox, judge, v5)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} solutions scored -> {args.out}")


if __name__ == "__main__":
    main()
