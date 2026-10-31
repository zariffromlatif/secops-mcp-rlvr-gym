"""Sample k answers per task from a model (optionally with a trained LoRA adapter) and score them
with every verifier. Run it on the base model before training, to see whether the tasks give a
learning signal at all, and on each trained adapter afterwards, on tasks it was not trained on.

    python -m train.evaluate --model Qwen/Qwen2.5-Coder-1.5B-Instruct --out results/train/eval-base
    python -m train.evaluate --model Qwen/Qwen2.5-Coder-1.5B-Instruct --adapter results/train/v3/final \\
        --tasks tasks_private --out results/train/eval-v3-heldout

Writes <out>/samples.jsonl and <out>/summary.json and prints one row per task:
    v1 v2 v3   mean reward of each verifier over the k answers
    solved     share of answers that solve the task (pass@1)
    any        at least one of the k answers solves it (pass@k)
    signal     the k answers got different v3 rewards, so GRPO can learn from this task
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from train.dataset import records
from train.grpo import REWARDS, completion_text
from train.scoring import ROOT, Scorer, extract_main


def summarize(rows: list[dict]) -> dict:
    """Per-task and overall means from scored samples ({"task", "v1", "v2", "v3", "solved"})."""
    tasks = {}
    for row in rows:
        tasks.setdefault(row["task"], []).append(row)
    per_task = {}
    for task, group in sorted(tasks.items()):
        n = len(group)
        per_task[task] = {
            "samples": n,
            **{k: sum(r[k] for r in group) / n for k in REWARDS},
            "solved": sum(r["solved"] for r in group) / n,
            "any": any(r["solved"] for r in group),
            "signal": len({round(r["v3"], 6) for r in group}) > 1,
        }
    n = len(per_task) or 1
    overall = {
        **{k: sum(t[k] for t in per_task.values()) / n for k in (*REWARDS, "solved")},
        "any": sum(t["any"] for t in per_task.values()) / n,
        "signal": sum(t["signal"] for t in per_task.values()) / n,
    }
    return {"tasks": per_task, "overall": overall}


def generate(model_name: str, adapter: Path | None, prompts: list[list[dict]], k: int, max_new_tokens: int,
             temperature: float) -> list[list[str]]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cuda = torch.cuda.is_available()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.bfloat16 if cuda else torch.float32)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter))
    model.to("cuda" if cuda else "cpu").eval()
    out = []
    for i, messages in enumerate(prompts, 1):
        text = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        batch = tokenizer([text] * k, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            ids = model.generate(**batch, do_sample=True, temperature=temperature, top_p=1.0,
                                 max_new_tokens=max_new_tokens, pad_token_id=tokenizer.pad_token_id)
        out.append(tokenizer.batch_decode(ids[:, batch["input_ids"].shape[1]:], skip_special_tokens=True))
        print(f"generated {i}/{len(prompts)}", flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--adapter", type=Path, help="a LoRA adapter saved by train.grpo (<out>/final)")
    parser.add_argument("--tasks", type=Path, nargs="+", default=[ROOT / "tasks"])
    parser.add_argument("--only", nargs="*", help="task ids (default: every task in --tasks)")
    parser.add_argument("-k", "--samples", type=int, default=8, help="answers per task")
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--temperature", type=float, default=1.0, help="as in training")
    parser.add_argument("--sandbox", choices=["warm", "local", "docker"], default="warm")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    data = [r for r in records(args.tasks) if not args.only or Path(r["task_dir"]).name in args.only]
    if not data:
        raise SystemExit("no tasks found")
    answers = generate(args.model, args.adapter, [r["prompt"] for r in data], args.samples,
                       args.max_new_tokens, args.temperature)
    scorer = Scorer(args.sandbox, args.workers)
    jobs = [(Path(r["task_dir"]), completion_text(a)) for r, group in zip(data, answers) for a in group]
    with ThreadPoolExecutor(args.workers) as pool:
        scores = list(pool.map(lambda job: scorer.score(job[0], extract_main(job[1])), jobs))
    rows = [{"task": folder.name, **{k: round(s[k], 4) for k in REWARDS}, "solved": s["solved"],
             "notes": s["notes"], "answer": text} for (folder, text), s in zip(jobs, scores)]
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "samples.jsonl").open("w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    summary = {"model": args.model, "adapter": str(args.adapter or ""), "k": args.samples, **summarize(rows)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n{'task':34} {'v1':>5} {'v2':>5} {'v3':>5} {'solved':>7} {'any':>4} signal")
    for task, t in summary["tasks"].items():
        print(f"{task:34} {t['v1']:5.2f} {t['v2']:5.2f} {t['v3']:5.2f} {t['solved']:7.0%} "
              f"{'yes' if t['any'] else '-':>4} {'yes' if t['signal'] else '-'}")
    o = summary["overall"]
    print(f"{'overall':34} {o['v1']:5.2f} {o['v2']:5.2f} {o['v3']:5.2f} {o['solved']:7.0%} {o['any']:4.0%} "
          f"{o['signal']:.0%} of tasks")


if __name__ == "__main__":
    main()
