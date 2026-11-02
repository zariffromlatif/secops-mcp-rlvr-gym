"""The whole V2-vs-V3 training comparison, one command per lab session. Each stage runs once; the
command stops cleanly before --deadline, and the same command next session continues.

    uv run --no-sync python -m train.campaign --deadline 12:40          # a session that must end at 12:40
    uv run --no-sync python -m train.campaign --steps 400 --evaluate-at 100 200   # no time limit

Stages, in order:
    check     the GPU is visible to PyTorch and free (stop Ollama first); a scorer that works:
              the warm Docker sandbox if Docker runs, else local mode with a Postgres at
              DATABASE_URL. The chosen one must score the gold fixes as solved and the buggy code
              as not, every session, before anything else runs.
    tasks     held-out tasks from a secret seed (tasks_private/; the secret lives in --secret-file,
              outside the repository) and extra training tasks (tasks_generated/), validated
    baseline  the base model, k answers per task, on the training and the held-out tasks
    train     the runs (v3 and v2) in chunks of --chunk steps, alternating, so they have the same
              number of steps whenever time runs out, and are compared fairly at that point
    evaluate  both runs' adapters on the training and the held-out tasks, at every milestone
              (--evaluate-at, and --steps itself), so a complete comparison exists at each one
    report    <out>/README.md, rewritten after every milestone: the runs over training, and every
              evaluation side by side

Without --deadline it runs until the last milestone is evaluated. Stopped for any reason (Ctrl+C,
a reboot, a crash), the same command continues from the last checkpoint.

Works on Linux and on Windows without WSL or admin rights: Docker Desktop for the warm sandbox, or
any Postgres for local mode (then check the answers afterwards with train.rescore on a machine with
Docker). On Windows it keeps the PC from sleeping while it runs. What is done is in
<out>/state.json, the full output in <out>/campaign.log.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from train.grpo import parse_deadline

ROOT = Path(__file__).resolve().parents[1]
TRAIN_TASKS = ["tasks", "tasks_generated"]
HELDOUT = "tasks_private"


def keep_awake() -> None:
    """On Windows, keep the PC from going to sleep while this process runs (needs no admin rights)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED


def docker_runs() -> bool:
    """A Docker engine answers. False, not an error, when Docker is not installed at all."""
    return shutil.which("docker") is not None and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


class Campaign:
    def __init__(self, args):
        self.args = args
        self.out = args.out
        self.out.mkdir(parents=True, exist_ok=True)
        self.state_path = self.out / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"done": []}
        self.deadline = parse_deadline(args.deadline)
        self.logfile = (self.out / "campaign.log").open("a", encoding="utf-8")

    # ------------------------------------------------------------------ plumbing
    def log(self, message: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        self.logfile.write(line + "\n")
        self.logfile.flush()

    def minutes_left(self) -> float:
        return (self.deadline - time.time()) / 60 if self.deadline else float("inf")

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n")

    def done(self, stage: str) -> bool:
        return stage in self.state["done"]

    def mark(self, stage: str) -> None:
        self.state["done"].append(stage)
        self.save()

    def python(self, *args: str, env: dict | None = None) -> int:
        """Run `python <args>` from the repository root, its output to the screen and the log."""
        self.log("$ python " + " ".join(args))
        child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **(env or {})}
        proc = subprocess.Popen([sys.executable, *args], cwd=ROOT, env=child_env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            print(line, end="", flush=True)
            self.logfile.write(line)
        self.logfile.flush()
        return proc.wait()

    def stop(self, why: str) -> None:
        self.log(f"stopping: {why}")
        self.status()
        raise SystemExit(0)

    def fail(self, why: str) -> None:
        self.log(f"FAILED: {why}")
        raise SystemExit(1)

    # ------------------------------------------------------------------ stages
    def check(self) -> None:
        probe = subprocess.run([sys.executable, "-c", (
            "import json, torch\n"
            "cuda = torch.cuda.is_available()\n"
            "free, total = torch.cuda.mem_get_info() if cuda else (0, 0)\n"
            "print(json.dumps({'cuda': cuda, 'name': torch.cuda.get_device_name(0) if cuda else '',"
            " 'free_gb': free / 2**30, 'total_gb': total / 2**30}))")],
            capture_output=True, text=True)
        if probe.returncode != 0:
            self.fail("PyTorch is missing: uv pip install -r train/requirements.txt (see docs/bracu-pc.md)")
        gpu = json.loads(probe.stdout.strip().splitlines()[-1])
        if gpu["cuda"]:
            self.log(f"GPU: {gpu['name']}, {gpu['free_gb']:.1f} of {gpu['total_gb']:.1f} GB free")
            if gpu["free_gb"] < self.args.min_free_gb:
                self.fail(f"only {gpu['free_gb']:.1f} GB of GPU memory free: something else holds it. If it is "
                          "Ollama: `ollama stop <model>` (or quit Ollama), then check with nvidia-smi")
        elif not self.args.allow_cpu:
            self.fail("PyTorch cannot see a CUDA GPU. On Windows, PyPI's torch is CPU-only: install the CUDA build "
                      "with the command from pytorch.org/get-started (pip -> uv pip install)")

        candidates = ["warm", "local"] if self.args.sandbox == "auto" else [self.args.sandbox]
        for sandbox in candidates:
            if sandbox == "warm" and not docker_runs():
                self.log("Docker is not installed or not running: no warm sandbox")
                continue
            self.log(f"checking the scorer with --sandbox {sandbox}: gold must be solved, buggy code not")
            if self.python("-m", "train.grpo", "--dry-run", "--sandbox", sandbox, "--workers", str(self.args.workers),
                           "--out", str(self.out / f"check-{sandbox}")) == 0:
                self.sandbox = sandbox
                self.state.setdefault("sandboxes", []).append({"at": time.strftime("%Y-%m-%d %H:%M"), "sandbox": sandbox})
                self.save()
                self.log(f"scorer: {sandbox}" + ("" if sandbox == "warm" else
                         " (not isolated: in-process tricks could pay off; re-score the answers with "
                         "train.rescore on a machine with Docker before reporting)"))
                return
        self.fail("no working scorer. Start Docker Desktop (warm sandbox), or run a Postgres and set DATABASE_URL "
                  "(local mode); see docs/bracu-pc.md")

    def tasks(self) -> None:
        if self.done("tasks"):
            return
        secret_file = self.args.secret_file.expanduser()
        if not secret_file.exists():
            secret_file.write_text(secrets.token_hex(16))
            secret_file.chmod(0o600)
            self.log(f"new held-out secret in {secret_file}: keep it, and keep it out of the repository")
        secret = secret_file.read_text().strip()
        for folder, count, extra, env in [
            (HELDOUT, self.args.heldout_count, [], {"GYM_FACTORY_SECRET": secret}),  # never on the command line
            ("tasks_generated", self.args.extra_count, ["--seed", "1", "--secret", ""], {}),
        ]:
            if not any((ROOT / folder).glob("*/task.yaml")):
                if self.python("-m", "factory.generate", "--count", str(count), *extra, "--out", folder, env=env):
                    self.fail(f"could not generate {folder}")
            if self.python("runtime/validate_tasks.py", "--tasks-dir", folder, "--sandbox", self.sandbox):
                self.fail(f"tasks in {folder} do not validate")
        self.mark("tasks")

    def milestones(self) -> list[int]:
        return sorted({m for m in self.args.evaluate_at if 0 < m < self.args.steps} | {self.args.steps})

    def evaluate(self, name: str, adapter: Path | None) -> None:
        """name/train and name/heldout evaluations, each skipped once it exists."""
        for split, folders in (("train", TRAIN_TASKS), ("heldout", [HELDOUT])):
            out = self.out / f"eval-{name}-{split}"
            if (out / "summary.json").exists():
                continue
            if self.minutes_left() < self.args.min_eval_minutes:
                self.stop(f"less than {self.args.min_eval_minutes} minutes left for the {name} {split} evaluation")
            args = ["-m", "train.evaluate", "--model", self.args.model, "--tasks", *folders, "-k", str(self.args.k),
                    "--max-new-tokens", str(self.args.max_completion_length), "--sandbox", self.sandbox,
                    "--workers", str(self.args.workers), "--out", str(out)]
            if adapter:
                args += ["--adapter", str(adapter)]
            if self.python(*args):
                self.fail(f"evaluation {out.name} failed")

    def steps_done(self, run: str) -> int:
        steps = [int(p.name.split("-")[1]) for p in (self.out / run).glob("checkpoint-*")]
        return max(steps, default=0)

    def train(self, target: int) -> None:
        runs = self.args.runs
        while True:
            done = {run: self.steps_done(run) for run in runs}
            pending = [run for run in runs if done[run] < target]
            if not pending:
                return
            self.log("steps so far: " + ", ".join(f"{run} {done[run]}/{target}" for run in runs))
            run = min(pending, key=lambda r: (done[r], runs.index(r)))  # the run that is behind
            if self.minutes_left() < self.args.min_chunk_minutes:
                self.stop(f"less than {self.args.min_chunk_minutes} minutes left for another chunk")
            goal = min(done[run] + self.args.chunk, target)
            started = time.time()
            deadline = ["--deadline", self.args.deadline] if self.args.deadline else []
            if self.python("-m", "train.grpo", "--model", self.args.model, "--reward", run, "--tasks", *TRAIN_TASKS,
                           "--steps", str(goal), "--out", str(self.out / run), "--resume", *deadline,
                           "--sandbox", self.sandbox, "--workers", str(self.args.workers),
                           "--batch", str(self.args.batch), "--grad-accum", str(self.args.grad_accum),
                           "--num-generations", str(self.args.num_generations),
                           "--max-completion-length", str(self.args.max_completion_length)):
                self.fail(f"training {run} failed")
            advanced = self.steps_done(run) - done[run]
            if advanced:
                pace = (time.time() - started) / advanced
                left = sum(self.args.steps - self.steps_done(r) for r in runs) * pace / 3600
                self.log(f"pace: {pace:.0f} s per step (model loading included); about {left:.1f} h of training left")
            if self.steps_done(run) < goal:
                if self.deadline:
                    self.stop("the deadline is near; the next session continues from the last checkpoint")
                self.fail(f"training {run} stopped at step {self.steps_done(run)}, before step {goal}; see the log above")

    def report(self) -> None:
        runs = [run for run in self.args.runs if (self.out / run / "samples.jsonl").exists()]
        if runs and self.python("-m", "train.report", *(str(self.out / run) for run in runs),
                                "--out", str(self.out / "README.md")):
            self.fail("report failed")
        rows = []
        evaluated = [("base", 0, "base")] + [(run, m, f"{run}-s{m}") for m in self.milestones() for run in self.args.runs]
        for model, steps, name in evaluated:
            for split in ("train", "heldout"):
                summary = self.out / f"eval-{name}-{split}" / "summary.json"
                if summary.exists():
                    o = json.loads(summary.read_text())["overall"]
                    rows.append(f"| {model} | {steps} | {split} | {o['v1']:.3f} | {o['v2']:.3f} | {o['v3']:.3f} "
                                f"| {o['solved']:.1%} | {o['any']:.1%} |")
        text = (self.out / "README.md").read_text() if (self.out / "README.md").exists() else "# Training runs\n"
        text += ("\n## Evaluations\n\n"
                 f"{self.args.model}, {self.args.k} answers per task; heldout: {HELDOUT}/ (secret seed). "
                 f"Scorer: {', '.join(sorted({s['sandbox'] for s in self.state.get('sandboxes', [])}))}.\n\n"
                 "| model | steps | tasks | v1 | v2 | v3 | solved (pass@1) | any solved (pass@k) |\n"
                 "|---|---:|---|---:|---:|---:|---:|---:|\n" + "\n".join(rows) + "\n")
        if any(s["sandbox"] == "local" for s in self.state.get("sandboxes", [])):
            text += ("\nScored in local mode, which is not isolated: check every answer in the warm sandbox with "
                     "`python -m train.rescore` (on a machine with Docker) before relying on these numbers.\n")
        (self.out / "README.md").write_text(text)
        self.log(f"report: {self.out / 'README.md'}")

    def status(self) -> None:
        steps = ", ".join(f"{run} {self.steps_done(run)}/{self.args.steps}" for run in self.args.runs)
        self.log(f"status: stages done {self.state['done']}; steps {steps}")

    def go(self) -> None:
        self.state.setdefault("model", self.args.model)
        if self.state["model"] != self.args.model:
            self.fail(f"this campaign uses {self.state['model']}; start a new one with another --out")
        self.save()
        self.log(f"session starts; {self.minutes_left():.0f} minutes until {self.args.deadline}" if self.deadline
                 else f"session starts, no deadline; milestones {self.milestones()} steps")
        self.check()
        self.tasks()
        if not self.done("baseline"):
            self.evaluate("base", None)
            self.mark("baseline")
        for milestone in self.milestones():
            self.train(milestone)
            if not self.done(f"evaluate@{milestone}"):
                # The weights at the milestone itself: its checkpoint, or the final adapter if no run went past it.
                adapters = {}
                for run in self.args.runs:
                    checkpoint = self.out / run / f"checkpoint-{milestone}"
                    adapters[run] = checkpoint if checkpoint.exists() else (
                        self.out / run / "final" if self.steps_done(run) == milestone else None)
                if None in adapters.values():
                    self.log(f"milestone {milestone} skipped: the runs are past it and its checkpoint is gone")
                    continue
                for run, adapter in adapters.items():
                    self.evaluate(f"{run}-s{milestone}", adapter)
                self.mark(f"evaluate@{milestone}")
            self.report()
        self.status()
        self.log("campaign complete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deadline", help="HH:MM local time to stop by (leave time to push results); none = no limit")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--runs", nargs="+", default=["v3", "v2"], choices=["v1", "v2", "v3"])
    parser.add_argument("--steps", type=int, default=100, help="training steps per run")
    parser.add_argument("--evaluate-at", type=int, nargs="*", default=[],
                        help="extra milestones (steps) at which both runs are evaluated; --steps always is")
    parser.add_argument("--chunk", type=int, default=25, help="steps per turn; runs alternate")
    parser.add_argument("-k", type=int, default=4, help="answers per task in evaluations")
    parser.add_argument("--heldout-count", type=int, default=3, help="held-out tasks per factory family")
    parser.add_argument("--extra-count", type=int, default=3, help="extra training tasks per factory family")
    parser.add_argument("--sandbox", choices=["auto", "warm", "local"], default="auto")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--max-completion-length", type=int, default=1536)
    parser.add_argument("--secret-file", type=Path, default=Path("~/.secops-gym-heldout-secret"))
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "train")
    parser.add_argument("--min-free-gb", type=float, default=12)
    parser.add_argument("--min-eval-minutes", type=float, default=30)
    parser.add_argument("--min-chunk-minutes", type=float, default=20)
    parser.add_argument("--allow-cpu", action="store_true", help="smoke tests with a tiny model only")
    args = parser.parse_args()
    # The training libraries' progress bars use block characters; a Windows console or pipe set to
    # cp1252 could not print them, and this process echoes them.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if shutil.which("git") is None:
        raise SystemExit("git is needed (patches are applied with git apply)")
    keep_awake()
    Campaign(args).go()


if __name__ == "__main__":
    main()
