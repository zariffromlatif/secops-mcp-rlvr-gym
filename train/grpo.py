"""GRPO on the patch tasks, with one verifier as the reward and every verifier logged.

The model gets a task (prompt, service code, public tests) and answers with a new app/main.py.
Each answer is scored by all three verifiers in one test run; the one named by --reward trains the
model, and all three go to <out>/samples.jsonl. Training on V1 (public tests only) while watching V3
shows whether, and how fast, the policy learns to pass the tests without fixing the bug.

    python -m train.grpo --dry-run                       # no model: score gold and buggy code, check the pipeline
    python -m train.grpo --model Qwen/Qwen2.5-Coder-7B-Instruct --reward v1 --out results/train/v1-run
    python -m train.report results/train/v1-run results/train/v3-run

Needs a GPU and the packages in train/requirements.txt; --dry-run needs only the Postgres from
runtime/docker-compose.yml.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from train.dataset import records
from train.scoring import ROOT, Scorer, extract_main

sys.path.insert(0, str(ROOT / "runtime"))
import score_patch as sp  # noqa: E402

REWARDS = ("v1", "v2", "v3")


def completion_text(completion) -> str:
    """TRL passes conversational completions as message lists and plain ones as strings."""
    if isinstance(completion, list):
        return "".join(m.get("content") or "" for m in completion if m.get("role") == "assistant")
    return completion


class Reward:
    """A TRL reward function: scores a batch in parallel, logs every verifier, returns the chosen one."""

    def __init__(self, choice: str, scorer: Scorer, out: Path, workers: int):
        self.choice, self.scorer, self.workers = choice, scorer, workers
        self.__name__ = f"reward_{choice}"
        out.mkdir(parents=True, exist_ok=True)
        self.samples = out / "samples.jsonl"
        self.lock = threading.Lock()

    def __call__(self, prompts, completions, task_dir, trainer_state=None, log_metric=None, **_) -> list[float]:
        step = trainer_state.global_step if trainer_state is not None else 0
        texts = [completion_text(c) for c in completions]
        with ThreadPoolExecutor(self.workers) as pool:
            results = list(pool.map(lambda job: self.scorer.score(Path(job[0]), extract_main(job[1])),
                                    zip(task_dir, texts)))
        with self.lock, self.samples.open("a") as fh:
            for folder, text, r in zip(task_dir, texts, results):
                fh.write(json.dumps({
                    "step": step, "task": Path(folder).name, "reward": self.choice,
                    **{k: round(r[k], 4) for k in REWARDS}, "solved": r["solved"], "notes": r["notes"],
                    "chars": len(text), "sha": hashlib.sha256(text.encode()).hexdigest()[:12],
                }) + "\n")
        if log_metric is not None:
            for key in REWARDS:
                log_metric(f"verifier/{key}", sum(r[key] for r in results) / len(results))
            log_metric("verifier/solved", sum(r["solved"] for r in results) / len(results))
        return [r[self.choice] for r in results]


def gold_main(task_dir: Path) -> str:
    sp.TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gold-", dir=sp.TMP_ROOT) as tmp:
        sp.prepare_workdir(task_dir, Path(tmp))
        assert sp.apply_patch(Path(tmp), task_dir / "gold.patch")[0], f"{task_dir.name}: gold patch does not apply"
        return (Path(tmp) / "app" / "main.py").read_text()


def dry_run(data: list[dict], reward: Reward) -> int:
    """Score the gold fix and the unchanged buggy code of every task through the training reward."""
    prompts, completions, folders = [], [], []
    for row in data:
        folder = Path(row["task_dir"])
        for code in (gold_main(folder), (folder / "app" / "main.py").read_text()):
            prompts.append(row["prompt"])
            completions.append([{"role": "assistant", "content": f"```python\n{code}```"}])
            folders.append(row["task_dir"])
    started = time.time()
    reward(prompts, completions, folders)
    rows = [json.loads(line) for line in reward.samples.read_text().splitlines()][-len(folders):]
    bad = []
    print(f"{'task':34} {'gold v1/v2/v3':>16} {'buggy v1/v2/v3':>16}")
    for gold, buggy in zip(rows[::2], rows[1::2]):
        fmt = lambda r: f"{r['v1']:.2f}/{r['v2']:.2f}/{r['v3']:.2f}"  # noqa: E731
        print(f"{gold['task']:34} {fmt(gold):>16} {fmt(buggy):>16}")
        if not gold["solved"] or buggy["solved"]:
            bad.append(gold["task"])
    print(f"{len(rows)} samples scored in {time.time() - started:.0f}s; written to {reward.samples}")
    if bad:
        print("FAIL: gold not solved or buggy code solved:", ", ".join(bad))
    return 1 if bad else 0


def train(args, data: list[dict], reward: Reward) -> None:
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import BitsAndBytesConfig
    from trl import GRPOConfig, GRPOTrainer

    config = GRPOConfig(
        output_dir=str(args.out),
        max_steps=args.steps,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        temperature=args.temperature,
        beta=args.beta,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=1,
        save_steps=args.save_steps,
        log_completions=True,
        use_vllm=args.vllm,
        vllm_mode="colocate",
        seed=args.seed,
        report_to=args.report_to,
    )
    quant = None
    if args.load_in_4bit:
        import torch

        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    trainer = GRPOTrainer(
        model=args.model,
        reward_funcs=[reward],
        args=config,
        train_dataset=Dataset.from_list(data),
        peft_config=LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, target_modules="all-linear",
                               task_type="CAUSAL_LM"),
        quantization_config=quant,
    )
    trainer.train()
    trainer.save_model(str(args.out / "final"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--reward", choices=REWARDS, default="v3", help="the verifier that trains the model")
    parser.add_argument("--tasks", type=Path, nargs="+", default=[ROOT / "tasks"],
                        help="task folders to train on, e.g. tasks tasks_generated")
    parser.add_argument("--hold-out", nargs="*", default=[], help="task ids left out of training")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "train" / "run")
    parser.add_argument("--sandbox", choices=["local", "docker"], default="local")
    parser.add_argument("--workers", type=int, default=8, help="samples scored at once")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--max-completion-length", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--beta", type=float, default=0.0, help="KL penalty")
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--vllm", action="store_true", help="generate with vLLM in the training process")
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report-to", default="none")
    parser.add_argument("--dry-run", action="store_true", help="score gold and buggy code, no model")
    args = parser.parse_args()

    data = [r for r in records(args.tasks) if Path(r["task_dir"]).name not in set(args.hold_out)]
    if not data:
        raise SystemExit("no tasks found")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "config.json").write_text(json.dumps(
        {k: str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v
         for k, v in vars(args).items()}, indent=2) + "\n")
    reward = Reward(args.reward, Scorer(args.sandbox, args.workers), args.out, args.workers)
    if args.dry_run:
        raise SystemExit(dry_run(data, reward))
    train(args, data, reward)


if __name__ == "__main__":
    main()
