# Training harness: does the verifier you train on decide what the model learns?

The audit measures verifiers on fixed solutions. This harness measures them where they matter: as the
reward in RL. Train one policy on V1 (public tests only) and one on V3 (the multi-gate reward), score
every sample of both with all verifiers, and compare.

## What a sample is

A single-turn version of the patch tasks. The prompt holds the task description, every file under
`app/` and `tests_public/`, and the answer format: the complete new `app/main.py` in one python code
block ([dataset.py](dataset.py)). The hidden tests are never shown. All 17 gold fixes change only
`app/main.py`, so every task can be solved in this format.

## Rewards

[scoring.py](scoring.py) runs the public and hidden tests once per answer and returns:

| key | reward | what it stands for |
|---|---|---|
| `v1` | share of public tests passing | a test-only verifier (audit V1) |
| `v2` | share of public + hidden tests passing | more tests, no other checks (audit V2) |
| `v3` | the multi-gate reward of [verifier/gates.py](../verifier/gates.py), normalized to 0-1 | the full verifier (audit V3) |
| `solved` | every test passes and the static gate is clean | the task is fixed |

An answer with no code block or with a syntax error scores 0 on all three without running tests.
The unchanged buggy code scores v1 = 1 on every task (public tests do not catch the bugs, by design)
and v3 around 0.5 (regression tests pass, target tests do not), so a V1-trained policy gets full
reward for changing nothing.

Where the answers run (`--sandbox`; seconds per sample and scoring worker, measured on a 4-CPU
machine):

| sandbox | per sample | isolated | |
|---|---|---|---|
| `warm` (default) | 1.7 s | yes | the scoring sandbox with its network, Postgres and test runner kept running (`runtime/warm_sandbox.py`) |
| `local` | 3.8 s | no | the app is imported into the test process, one Postgres database per worker; needs no Docker, but in-process tricks can pay off |
| `docker` | 7.5 s | yes | the sandbox built from scratch for every sample |

Report results from an isolated run: a reward the policy can game in-process measures the sandbox,
not the verifier.

## Which rewards to compare

In this single-turn format the answer is only `app/main.py`, so editing tests or seed data is
impossible, and the sandbox closes in-process tricks. What is left for a reward to get wrong:

- **V1** pays the unchanged buggy code in full (public tests don't catch the bugs), so most groups
  of answers get the same reward and GRPO has almost nothing to learn from. A V1 run shows how
  little a test-only reward teaches; it can't show cheating.
- **V2** pays every answer that passes all tests, including SQL built from strings, which only V3's
  static gate rejects. Its `gamed v2` rate (all tests pass, not solved) is the one to watch.
- **V3** is the full reward.

The informative pair is **V2 vs V3**, same model, seed and steps; add V1 if time allows. Evaluate both
adapters on tasks they weren't trained on, so learning the tasks by heart doesn't count as learning
to fix bugs.

## Running

```bash
uv pip install -r train/requirements.txt     # CUDA GPU; these packages are not in the main lockfile

# 0. No model: score every gold fix and every buggy original through the training reward.
uv run --no-sync python -m train.grpo --dry-run

# 1. Held-out tasks nobody else can rebuild (keep the secret outside the repository)
export GYM_FACTORY_SECRET="$(openssl rand -hex 16)"
uv run --no-sync python -m factory.generate --count 3 --out tasks_private
uv run --no-sync python -m factory.generate --count 3 --seed 1 --secret "" --out tasks_generated  # more training tasks
uv run --no-sync python runtime/validate_tasks.py --tasks-dir tasks_private --sandbox warm
uv run --no-sync python runtime/validate_tasks.py --tasks-dir tasks_generated --sandbox warm

# 2. Baseline: does the base model get partial credit, with different rewards across its answers?
uv run --no-sync python -m train.evaluate -k 8 --out results/train/eval-base
uv run --no-sync python -m train.evaluate -k 8 --tasks tasks_private --out results/train/eval-base-heldout

# 3. Smoke run: 2 steps, to measure seconds per step and GPU memory (watch nvidia-smi)
uv run --no-sync python -m train.grpo --steps 2 --out results/train/smoke

# 4. The runs (--resume continues after a session ends)
uv run --no-sync python -m train.grpo --reward v3 --tasks tasks tasks_generated --steps 200 --out results/train/v3
uv run --no-sync python -m train.grpo --reward v2 --tasks tasks tasks_generated --steps 200 --out results/train/v2

# 5. Compare
uv run --no-sync python -m train.report results/train/v2 results/train/v3 --out results/train/README.md
uv run --no-sync python -m train.evaluate -k 8 --tasks tasks_private --adapter results/train/v3/final \
    --out results/train/eval-v3-heldout     # and the same for v2
```

`uv run --no-sync` keeps uv from removing the training packages, which aren't in the lockfile.

[grpo.py](grpo.py) wraps TRL's `GRPOTrainer` with a LoRA adapter (`--lora-r`, default 16). Each step
scores 32 answers: 4 tasks x 8 answers (`--batch 4 --grad-accum 8 --num-generations 8`). Every
scored answer is appended to `<out>/samples.jsonl` with its step, task, v1/v2/v3, `solved` and the gate
notes; the means also go to the trainer's logs as `verifier/*`. A checkpoint is saved every 25 steps
and `--resume` continues from the last one. `--hold-out <task ids>` keeps tasks out of training.

[evaluate.py](evaluate.py) samples k answers per task from the base model or a trained adapter and
scores them: mean v1/v2/v3, pass@1, pass@k, and whether a task gives a learning **signal** (its
answers got different rewards). Tasks where every answer gets the same reward teach GRPO nothing;
if most tasks have no signal, pick a stronger or weaker model.

[report.py](report.py) prints, per block of steps, the mean of each verifier, the solved rate and
two **gamed** rates: v1 = 1 but not solved (the unchanged code is there), and v2 = 1 but not solved
(every test passes, the full verifier rejects it).

## On a 16 GB GPU (RTX 4080 Super)

Prompts are 900-1,700 tokens and gold answers 160-880 (Qwen2.5 tokenizer), so the default
`--max-completion-length 1536` is enough.

| Model | How | Fits |
|---|---|---|
| Qwen2.5-Coder-1.5B-Instruct (default) | bf16 + LoRA | yes, with room to spare: start here |
| Qwen2.5-Coder-3B-Instruct | bf16 + LoRA | likely; lower `--batch` to 2 (and raise `--grad-accum` to 16) if it runs out of memory |
| Qwen2.5-Coder-7B-Instruct | `--load-in-4bit` (QLoRA) | tight, and generation is slow in 4-bit; not for a first run |

Generation will take most of each step; scoring 32 answers with 8 warm workers takes about 7 s.
Measure seconds per step in the smoke run before planning: 200 steps at 90 s each is 5 hours.

No training run is checked in yet. CI runs `--dry-run`, [tests/test_train.py](../tests/test_train.py)
and a 2-step training plus evaluation with a tiny model on CPU, so the code path you run on the GPU
is exercised on every push.
