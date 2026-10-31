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

`--sandbox local` (default) imports the app into the test process with one Postgres database per
scoring worker: a few seconds per sample, not isolated. `--sandbox docker` uses the scoring sandbox
of `runtime/sandbox.py`: isolated, slower.

## Running

```bash
docker compose -f runtime/docker-compose.yml up -d --wait

# No model, no GPU: score every gold fix and every buggy original through the training reward.
uv run python -m train.grpo --dry-run

# Training (CUDA GPU; packages not in the main lockfile)
uv pip install -r train/requirements.txt
uv run python -m train.grpo --model Qwen/Qwen2.5-Coder-7B-Instruct --reward v1 --out results/train/v1 \
    --load-in-4bit --steps 200
uv run python -m train.grpo --model Qwen/Qwen2.5-Coder-7B-Instruct --reward v3 --out results/train/v3 \
    --load-in-4bit --steps 200
uv run python -m train.report results/train/v1 results/train/v3 --out results/train/README.md
```

[grpo.py](grpo.py) wraps TRL's `GRPOTrainer` with a LoRA adapter (`--lora-r`, default 16) and
optional 4-bit loading. Every scored sample is appended to `<out>/samples.jsonl` with its step, task,
v1/v2/v3, `solved` and the gate notes; v1/v2/v3/solved means also go to the trainer's logs as
`verifier/*`. `--tasks tasks tasks_generated` adds factory tasks (see [factory/](../factory));
`--hold-out <task ids>` keeps tasks out of training.

[report.py](report.py) prints, per block of steps, the mean of each verifier, the solved rate and the
**gamed** rate: samples with v1 = 1 that are not solved, i.e. answers a test-only verifier pays in
full that the full verifier rejects. A V1 run whose v1 climbs while solved stays flat and gamed grows
is learning the tests, not the fixes.

No training run is checked in: this container has no GPU. CI runs `--dry-run` and
[tests/test_train.py](../tests/test_train.py).
