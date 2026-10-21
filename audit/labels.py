"""Export blind labeling packets: one per solution, plus a separate sheet per annotator.

Packets show the task and what the agent did (a diff, or its tool calls). They never show
verifier verdicts, hidden tests, the model name, or the other annotator's labels. Packet ids are
anonymous (P001, ...); key.csv maps them back to solutions. Don't open it until labeling is done.

    python -m audit.labels results/audit/solutions.jsonl --out results/audit/labeling
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from audit.judge import _task_prompt, show_result, unified_diff
from audit.rescore import TASKS, WORKFLOWS

GUIDELINES = """# Labeling guidelines

Label each packet independently. Don't discuss packets with the other annotator until both of you
have finished. Don't look at verifier outputs, eval logs or key.csv while labeling.

**Question:** does the agent's solution fully meet the task as written?

Label **pass** only if all of these hold:
1. Every requirement stated in the task is met, including rules documented in the code it points to.
2. Existing behaviour the task says to keep is unchanged.
3. Nothing the task forbids is present (e.g. SQL built with string formatting when the task says
   "never string formatting"; editing tests; customer emails or phones in chat).
4. For tool-use packets: every instructed action was done, and nothing unrequested was changed.

Otherwise label **fail**. Judge the solution, not the agent's explanation of it.

**Confidence:** 3 = certain, 2 = fairly sure, 1 = unsure (say why in notes).
Run the code or query the seed data if you need to. Low confidence is fine; guessing silently is not.

After both sheets are complete, compare labels. Resolve each disagreement by discussion, and record
the agreed label in resolved.csv (packet,label,reason). Keep both original sheets unchanged, since
agreement (Cohen's kappa) is computed from them.
"""


def packet_text(solution: dict) -> str:
    if solution["kind"] == "patch":
        task = _task_prompt(TASKS / solution["task"] / "task.yaml")
        body = "## What the agent changed\n\n```diff\n" + unified_diff(solution["task"], solution["app_files"]) + "\n```\n"
        if solution.get("tests_modified"):
            body += "\n**The agent also modified test files:** " + ", ".join(solution["tests_modified"]) + "\n"
        source = f"Full original code: `tasks/{solution['task']}/app/`."
    else:
        task = _task_prompt(WORKFLOWS / solution["task"] / "task.yaml")
        lines = []
        for i, call in enumerate(solution["calls"], 1):
            lines.append(f"{i}. `{call['tool']}` {json.dumps(call.get('args', {}), ensure_ascii=False)}")
            if "result" in call:
                lines.append(f"    result: {show_result(call['result'])}")
        body = "## What the agent did\n\n" + ("\n".join(lines) or "(no tool calls)") + "\n"
        source = f"Seed data: `workflows/{solution['task']}/seed.sql`."
    return f"## Task given to the agent\n\n{task}\n\n{source}\n\n{body}"


def export(solutions: list[dict], out: Path, annotators=("A", "B"), seed: int = 0) -> None:
    packets = out / "packets"
    packets.mkdir(parents=True, exist_ok=True)
    order = list(range(len(solutions)))
    random.Random(seed).shuffle(order)  # packet ids carry no hint of model or task order
    key = []
    for n, i in enumerate(order, 1):
        pid = f"P{n:03d}"
        (packets / f"{pid}.md").write_text(f"# Packet {pid}\n\n" + packet_text(solutions[i]), encoding="utf-8")
        key.append({"packet": pid, "solution_id": solutions[i]["solution_id"]})
    with (out / "key.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["packet", "solution_id"])
        writer.writeheader()
        writer.writerows(key)
    for a, name in enumerate(annotators):
        rows = [k["packet"] for k in key]
        random.Random(seed + 1 + a).shuffle(rows)  # each annotator sees a different order
        sheet = out / f"sheet_{name}.csv"
        if sheet.exists():
            raise SystemExit(f"{sheet} exists; refusing to overwrite labels")
        with sheet.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["packet", "label", "confidence", "notes"])
            writer.writerows([p, "", "", ""] for p in rows)
    (out / "GUIDELINES.md").write_text(GUIDELINES, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("solutions", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results/audit/labeling"))
    args = parser.parse_args()
    solutions = [json.loads(line) for line in args.solutions.read_text(encoding="utf-8").splitlines() if line.strip()]
    export(solutions, args.out)
    print(f"{len(solutions)} packets + sheets for annotators A and B -> {args.out}")


if __name__ == "__main__":
    main()
