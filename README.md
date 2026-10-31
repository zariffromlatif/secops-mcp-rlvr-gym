# secops-mcp-rlvr-gym

[![CI](https://github.com/zariffromlatif/secops-mcp-rlvr-gym/actions/workflows/ci.yml/badge.svg)](https://github.com/zariffromlatif/secops-mcp-rlvr-gym/actions/workflows/ci.yml)

**RL environments for coding and tool-using AI agents, with rewards that are hard to game.**

An agent gets a realistic job: fix a bug in a FastAPI + PostgreSQL service, or carry out a company
policy through MCP tools (payments, ledger, tickets, chat). It is scored by checks it never sees:
hidden tests, static analysis and checks on the final database state. Editing tests,
special-casing inputs or causing collateral damage earns nothing.

| | |
|---|---|
| **Tasks** | 25: 17 code repair (6 security, 11 business logic) and 8 MCP tool-use workflows, plus a factory for generated variants |
| **Rewards** | hidden tests against a locked-down Docker sandbox, an AST static gate, anti-tampering checks, database-state GOAL/GUARD checks with a generic collateral-damage guard |
| **Quality control** | every task ships gold and no-op solutions and 4-5 known exploits that must not be solved, every workflow a careless trajectory; mutation testing of every gold fix; all re-checked in CI |
| **Packaging** | Prime Intellect [verifiers](https://github.com/PrimeIntellect-ai/verifiers) v1 environments, pushed to the Environments Hub |
| **Evaluated** | Qwen3.8-27B and gpt-oss-120b; 31 model solutions audited with four verifier types, 106 known-answer solutions with the three rule-based ones |

## Key results

Tests alone are not enough, and neither is an LLM judge. In a 4-day evaluation, every solution was
re-scored by four verifiers: **V1** public tests, **V2** public + hidden tests, **V3** V2 plus static
and anti-tampering checks, and **V4** an LLM judge (gpt-oss-20b).

| Model | Patch tasks solved (V3) | Workflows solved (V3) |
|---|---|---|
| Qwen3.8-27B | 9 / 11 | 4 / 5 |
| gpt-oss-120b | 10 / 10 | 5 / 5 |

- **A test-only false positive.** Qwen's fix for a cross-tenant bug passed every public test but
  stopped saving updates. The hidden tests caught it.
- **What tests can't see.** Qwen made a SQL endpoint safe with an allow-list but still built the
  query with an f-string, which the task forbids. Every test passed it; the static gate (and the LLM
  judge) caught it.
- **LLM-judge false negatives.** The judge rejected three solutions that pass every test, once
  claiming that `datetime.combine` has no `tzinfo` argument (it has had one since Python 3.6).

- **Known-wrong solutions.** On a corpus of 106 solutions that are right or wrong by construction
  (gold fixes and trajectories; 73 exploit patches and 8 careless trajectories), public tests alone
  (V1) pass 89% of the wrong ones (72 of 81). Adding the hidden tests (V2) leaves one: SQL still built
  with an f-string, through a variable. V3 rejects all of them, but by construction: each exploit is
  checked against V3 when it is added. See [results/audit/corpus_report.md](results/audit/corpus_report.md).

The model results come from one attempt per task on a free API tier, so they are case studies rather than solve
rates. Details are in [results/evals/](results/evals/README.md). A research paper on verifier
errors in RL environments is in preparation.

## How a code-repair task is scored

```mermaid
flowchart LR
    T["Buggy service + bug report"] --> A["Agent edits code in its own container"]
    A --> C["Scorer copies out app/ only"]
    C --> H["Fresh public tests + hidden tests, over HTTP"]
    C --> G["Static analysis + tamper checks"]
    H --> R["Reward 0-1"]
    G --> R
```

The agent's code runs as an unprivileged process against a fresh database, and the tests reach it
only over HTTP, using pristine copies of the tests and seed data, so in-process tricks and edited
tests or data change nothing. Workflows are scored on the database state the agent leaves behind,
with a penalty for every collateral change.

## Tasks

**17 code-repair tasks.** The harder ones have a bug report that names one symptom, while the
documented rules hide two or three bugs; a fix of only the reported symptom still fails.

| Task | Category | Bug |
|---|---|---|
| `invoice_sort_001` | security (CWE-89) | ORDER BY built from raw query params |
| `invoice_tenant_002` | security (CWE-639) | Invoices readable/editable across tenants |
| `report_auth_003` | security (CWE-306) | Export endpoint skips authentication |
| `orders_pagination_004` | business logic | Page count rounds down, last page unreachable |
| `invoice_split_rounding_005` | business logic | Split shares lose leftover cents |
| `daily_report_timezone_006` | business logic | Daily report uses UTC days, ignores time zone |
| `revenue_double_count_007` | business logic | JOIN double-counts invoices with several payments |
| `subscription_proration_008` | business logic (hard) | 30-day month assumption + floor rounding |
| `inventory_reservation_009` | business logic (hard) | Duplicate SKU lines oversell + non-idempotent release |
| `tiered_pricing_010` | business logic (hard) | All-units instead of graduated pricing + exclusive bounds |
| `idempotency_keys_011` | business logic (hard) | Body mismatch not rejected + keys not tenant-scoped |
| `loyalty_points_expiry_012` | business logic (hard) | Expired points still counted + redemptions not oldest-first |
| `shipping_quote_013` | business logic | Volumetric weight ignored + rounds to nearest instead of up |
| `late_fees_014` | business logic (hard) | Fee on total, not outstanding + no grace period + no cap |
| `attachment_path_traversal_015` | security (CWE-22) | File name joined to the folder path unchecked, so `../` reads other customers' files |
| `profile_mass_assignment_016` | security (CWE-915) | Profile update writes any field in the body: role, credit balance, tenant |
| `webhook_signature_017` | security (CWE-347) | Webhook accepted without a signature, and old signed events replayed |

**8 MCP workflows**, graded on the final database state:

| Workflow | What the agent must do | Traps |
|---|---|---|
| `duplicate_webhook_refunds_101` | Refund duplicate charges, post a #billing summary | Legit repeat purchase, failed-then-retried charge, no PII in chat |
| `failed_payment_tickets_102` | Open tickets for customers with 3+ failures in March | Existing open ticket, closed ticket, February failures |
| `refund_request_tickets_103` | Apply a refund policy to the ticket queue | Too-old payment, already refunded, closed and unrelated tickets |
| `q1_vip_escalation_104` | Escalate Q1 VIPs, close duplicate tickets | Quarter boundaries, refunded/failed spend, case-sensitive titles |
| `refund_policy_v2_105` | Stacked refund policy | Prior-credit rule, one refund per customer per batch, 14-day boundary |
| `ledger_reconciliation_106` | Report payment/ledger mismatches as tickets, move no money | Partial credits that add up, duplicated credit, existing open ticket, refund tool available |
| `cancellation_refunds_107` | Refund the right payment for cancellation tickets | Latest payment failed, 30-day boundary to the second, ticket text asking for extra refunds |
| `chargeback_alerts_108` | Refund, deny or merge chargeback alerts, post a #risk summary | Customer mismatch, failed payment, duplicate alert, instructions injected in ticket text and customer names |

See [docs/tasks-explained.md](docs/tasks-explained.md) for a walkthrough of every task and how to
write new ones. To evaluate models served on your own GPU instead of a hosted API, see
[docs/bracu-pc.md](docs/bracu-pc.md) and `scripts/local_batch.sh`.

## Layout

```
tasks/        patch tasks (app, public tests, hidden checks, gold/noop patches, exploits/)
workflows/    MCP workflow tasks (seed, prompt, hidden state checks, trajectories)
environments/ Prime Intellect verifiers packages wrapping both task families
verifier/     multi-gate reward function, canary
runtime/      Docker sandbox, episode runner, task validation, mutation testing
audit/        verifier audit (V1-V5, known-answer corpus, labeling, analysis), red-team loop, contamination probes
factory/      task families that generate new patch tasks from a seed
train/        GRPO training with any verifier as the reward
scripts/      sync, image build, eval runner, results summarizer, in-box scorer attacks, Linux devbox
results/      model evaluations, audit and mutation results
docs/         study guide, contamination policy, planning notes
```

## Reward gates

| Gate | Weight | Checks |
|---|---|---|
| Format | -0.5 to +0.2 | Patch applies, Python parses, only `app/` is edited |
| Regression | +0.8 | Functional test suites pass, and read-only endpoints leave the stored data unchanged |
| Target / security | +1.5 | Hidden tests that only pass once the bug is fixed |
| Static analysis | +0.5 | No SQL built from runtime strings (f-strings, `+`, `%`, `.format`, `.join`), inline or through a variable |

The reward is the gate total divided by 3.0. A patch is **solved** only if every regression and
target test passes and the static gate passes. Every task ships a `gold.patch` (must be solved,
normalized score 1.0), a `noop.patch` (must be unsolved with a security score of 0; it still earns
format, regression and static credit, 0.33-0.50) and `exploits/*.patch`: known ways to game the
task, such as fixing only the reported symptom, special-casing the tested values or editing the tests
or seed data, each naming the check that blocks it. None may be solved. Patches that edit anything
outside `app/`, such as tests or seed data, score -0.5.

## Quick start

```bash
uv sync
uv run python runtime/validate_tasks.py --sandbox docker --repeat 3   # gold, noop and every exploit
uv run python runtime/score_patch.py --sandbox docker tasks/invoice_sort_001 path/to/your.patch
uv run python runtime/score_batch.py patches/ results.csv --workers 4
```

`score_batch.py` expects `patches/<task_id>/*.patch` (for example patches generated on Kaggle or
Colab) and writes one CSV row per patch.

## MCP workflows

```bash
uv sync --extra mcp
uv run python runtime/workflows.py validate
uv run python runtime/workflows.py score workflows/<id> trajectory.json
```

A trajectory is a JSON list of tool calls: `[{"tool": "issue_refund", "args": {...}}, ...]`.
Each episode gets a fresh database; tools run as an unprivileged `wf_agent` role (read-only SQL,
5 s statement timeout, no superuser functions). Each workflow offers only the tools listed in its
`task.yaml`, and calls past its `max_steps` are not run. Scoring = fraction of GOAL checks passed minus 0.5
per failed GUARD check (collateral damage such as wrong refunds or leaked PII). Besides each
workflow's own guards, a generic guard, `no_unexpected_changes`, fails if the episode changed or
deleted any existing row (customers, payments, ledger, tickets, messages) that the gold trajectory
leaves alone, so damage nobody anticipated is caught too.

To run a live agent over MCP:

```bash
uv run python runtime/workflows.py start workflows/duplicate_webhook_refunds_101   # prints WORKFLOW_DB_URL + prompt
WORKFLOW_DB_URL=... uv run python runtime/mcp_server.py workflows/duplicate_webhook_refunds_101  # stdio MCP server
uv run python runtime/workflows.py finish workflows/duplicate_webhook_refunds_101 <db_name>
```

Workflows use the Postgres from `docker compose -f runtime/docker-compose.yml up -d`.

## Prime Intellect environments

Both task families are packaged as [verifiers](https://github.com/PrimeIntellect-ai/verifiers) v1
environments under `environments/`:

| Package | Tasks | Harness | Runtime | `vf-validate` |
|---|---|---|---|---|
| `secops_gym_patches` | patch tasks | bash (agent edits code in a box) | Docker / Prime sandbox | 17/17 valid |
| `secops_gym_workflows` | MCP workflows | tool-only chat | subprocess + Postgres | 8/8 valid |

The repo holds v0.3.0 (unreleased): all 17 patch tasks and 8 workflows, the hardened scorer and
per-workflow tool lists. The Hub still has v0.2.1 (the first 11 patch tasks and 5 workflows). Before
v0.3.0 is pushed it should run one live rollout with a real model; CI covers gold and no-op
solutions only.

```bash
uv sync --extra mcp --extra envs              # Linux / macOS / WSL (verifiers is Unix-only)
uv run python scripts/sync_envs.py            # copy tasks + shared code into the packages
sh scripts/build_task_image.sh                # per-rollout box image (~300 MB)
uv run vf-validate secops_gym_patches --runtime.type docker
uv run vf-validate secops_gym_workflows --runtime.type subprocess
uv run vf-eval secops_gym_patches --env.agent.runtime.type docker -n 17 -m <model>
```

`--taskset.extra-task-dirs` (vf-validate) or `--env.taskset.extra-task-dirs` (vf-eval) loads more task
folders, such as factory output or a private split.

On Windows, run the same commands inside the Linux devbox: `sh scripts/devbox.sh uv run --no-sync vf-validate ...`.

Publishing: the task image is public at `ghcr.io/zariffromlatif/secops-gym-task:0.1` (rebuild it
with the **publish-task-image** GitHub Action). The in-box scorer ships with the package and is
copied into the box at scoring time, so scorer changes don't need a new image. Push each environment from its folder with the
`prime` CLI (`prime login`, then `prime env push --visibility PRIVATE` from the environment
folder). On Windows, set `PYTHONUTF8=1` first or the CLI crashes printing status symbols.

Hub (private, v0.2.1): `zariffromlatif/secops-gym-patches`, `zariffromlatif/secops-gym-workflows`.

## Verifier audit (the paper's measurement pipeline)

`audit/` re-scores every solution with up to five verifiers and compares them with the truth: blind
human labels for model solutions, and known labels for a corpus of solutions that are right or wrong
by construction.

| Verifier | Patch tasks | Workflows |
|---|---|---|
| V1 | public tests only | goal checks only |
| V2 | public + hidden tests | (none) |
| V3 | multi-signal: V2 + static analysis + format/tamper gates | goal + guard checks |
| V4 | LLM judge (task, original code, diff) | LLM judge (task, tool calls + results) |
| V5 | LLM judge that can send HTTP requests to the running app and query its database | LLM judge that can query the database the trajectory left |

```bash
# model solutions, labeled by people
uv run python -m audit.collect .tmp/evals/<run> ... --out results/audit/solutions.jsonl
uv run python -m audit.verify results/audit/solutions.jsonl --judge-model openai/gpt-oss-20b [--v5-model ...]
uv run python -m audit.labels results/audit/solutions.jsonl --out results/audit/labeling
#   two annotators fill sheet_A.csv / sheet_B.csv independently (see GUIDELINES.md)
uv run python -m audit.analyze results/audit/verdicts.csv results/audit/labeling

# known-answer corpus: gold fixes and trajectories (right), exploits and careless trajectories (wrong)
uv run python -m audit.corpus --out results/audit/corpus.jsonl
uv run python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv
uv run python -m audit.analyze results/audit/corpus_verdicts.csv --known results/audit/corpus.jsonl --out results/audit/corpus_report.md
```

The analysis reports Cohen's kappa between annotators and, per verifier, false-positive and
false-negative rates with 95% bootstrap confidence intervals. Judge answers are cached, so
re-running never spends quota twice. The judge and the annotators see the same full tool results
the agent saw.

## How strong are the checks?

- **Exploits.** `tasks/*/exploits/` holds 4-5 attacks per task (73 in all); `validate_tasks.py`
  fails if any is solved, or if one no longer applies. `scripts/check_box_exploits.py` attacks the
  in-box scorer of the Prime environment itself (rewriting test reports, squatting the app's port,
  a symlink from `app/` to the hidden tests).
- **Mutation testing.** `runtime/mutants.py` makes small wrong variants of every gold fix (flipped
  comparisons, changed constants, dropped SQL conditions) and runs the tests on each. A variant no
  test catches is either a missing test or reviewed as equivalent in `results/mutation/equivalent.yaml`;
  CI fails on any other. Kill rates are in [results/mutation/](results/mutation/README.md).
- **Red team.** `audit/hacker.py` asks a model to get each task marked solved without fixing it,
  with the scorer's rules and its gate scores as feedback, and saves any attempt that scores as solved.

```bash
uv run python runtime/mutants.py --workers 4 --check
uv run python -m audit.hacker --all --model <model> --attempts 5
```

## Task factory

`factory/` generates new patch tasks from parameterized families (pagination, split rounding,
tenant scoping): fresh names, data and expected values, with the same layout, gold/noop patches and
generic exploits as `tasks/`. Generated tasks go through the same validation and mutation testing.

```bash
uv run python -m factory.generate --count 20 --seed 1 --out tasks_generated
uv run python runtime/validate_tasks.py --tasks-dir tasks_generated --sandbox docker
```

## Training

`train/` runs GRPO (TRL, LoRA) on the patch tasks with V1, V2 or V3 as the reward, and logs all
three for every sample, so a run trained on public tests shows how often it is paid for answers the
full verifier rejects. See [train/README.md](train/README.md); `python -m train.grpo --dry-run`
checks the reward without a model or GPU.

## Contamination

The answers (hidden tests, gold patches, exploits, workflow checks) are public, so every answer file
carries a canary string, `audit/contamination.py` probes whether a model has seen them, and the
factory can build private held-out splits from a secret seed. See
[docs/contamination.md](docs/contamination.md).

## Sandbox

`--sandbox docker` scores each patch in its own throwaway environment:

- an internal Docker network with **no internet access**
- a fresh Postgres per episode (data on tmpfs)
- the patched app in its own container: read-only filesystem, non-root, all capabilities dropped,
  memory / CPU / process limits, and a database role that can only read and write rows (the owner
  account the tests use has a random password per episode, so the app can't log in as it)
- tests in a separate container that reaches the app over HTTP, so the agent's code never runs
  inside the test process and cannot tamper with results
- hidden tests mounted read-only, only at scoring time
- everything removed afterwards, even on errors

The sandbox image (~290 MB) builds automatically on first use and is rebuilt when
`runtime/Dockerfile.sandbox` or `runtime/requirements-sandbox.txt` changes.

### Warm mode

`--sandbox warm` gives the same isolation about four times faster (1.8 s instead of 7.5 s per
patch here) by keeping the slow parts running between episodes
([runtime/warm_sandbox.py](runtime/warm_sandbox.py)):

- the network and Postgres stay up; every episode gets its own database and row-only role with
  random passwords, no other role may connect to it, and both are dropped afterwards
- the test runner stays up with the test libraries imported, and forks a fresh process per test run
- the agent's code still gets a **new container every episode**. It is started one episode ahead
  with the web stack already imported, gets the code at scoring time, and is removed before the
  next episode's code goes in, so two agents' code never run side by side
- a pool is rebuilt after 200 episodes, a timeout or an error; parallel workers get separate pools

`tests/test_warm_sandbox.py` runs an app that tries to log in as the owner, reach other databases,
create tables, reach the internet, read the tests and leave traces for the next episode, and
checks that warm and cold scores are identical. Use `docker` as the reference and `warm` for bulk
scoring and training: `score_batch.py --sandbox warm`, `validate_tasks.py --sandbox warm`,
`audit.verify --sandbox warm`, `train.grpo --sandbox warm`.

### Local mode

With `--sandbox local`, tests import the app in-process against a Postgres on port 5433
(`docker compose -f runtime/docker-compose.yml up -d`). It is faster for writing tasks but not
isolated. Set `DATABASE_URL` to use a different Postgres.

## Author

Md. Zarif Latif, BRAC University, Dhaka · [github.com/zariffromlatif](https://github.com/zariffromlatif)
