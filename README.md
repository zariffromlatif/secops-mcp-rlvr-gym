# secops-mcp-rlvr-gym

Containerized RLVR (Reinforcement Learning with Verifiable Rewards) environments for training and
evaluating code agents on backend security remediation in FastAPI + PostgreSQL services.

An agent receives a small service with a known security flaw and a bug report, and must return a
patch. The patch is scored by deterministic checks the agent never sees during its rollout, so the
reward cannot be gamed by editing tests or special-casing inputs.

## Status

11 patch tasks, all validated in the Docker sandbox (gold solved at 1.00, no-op unsolved with zero
target score, identical scores across 3 runs):

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

Plus 5 **MCP workflow** tasks, where an agent operates mock company tools (read-only SQL,
refunds, tickets, chat) and is graded on the final database state:

| Workflow | What the agent must do | Traps |
|---|---|---|
| `duplicate_webhook_refunds_101` | Refund duplicate charges, post a #billing summary | Legit repeat purchase, failed-then-retried charge, no PII in chat |
| `failed_payment_tickets_102` | Open tickets for customers with 3+ failures in March | Existing open ticket, closed ticket, February failures |
| `refund_request_tickets_103` | Apply a refund policy to the ticket queue | Too-old payment, already refunded, closed and unrelated tickets |
| `q1_vip_escalation_104` | Escalate Q1 VIPs, close duplicate tickets | Quarter boundaries, refunded/failed spend, case-sensitive titles |
| `refund_policy_v2_105` | Stacked refund policy | Prior-credit rule, one refund per customer per batch, 14-day boundary |

**Model evaluations:** Qwen3.8-27B solved 9/10 of the first tasks. On `invoice_sort_001`, the static
gate caught an f-string SQL fix that the tests alone would have accepted. On the harder set,
gpt-oss-120b fixed only the reported half of `inventory_reservation_009`. See
[results/evals/](results/evals/README.md).

See [docs/tasks-explained.md](docs/tasks-explained.md) for a walkthrough of every task and how to
write new ones.

## Layout

```
tasks/        patch tasks (app, public tests, hidden checks, gold/noop patches)
workflows/    MCP workflow tasks (seed, prompt, hidden state checks, trajectories)
environments/ Prime Intellect verifiers packages wrapping both task families
verifier/     multi-gate reward function
runtime/      Docker sandbox and episode runner
training/     GRPO training and evaluation scripts
thesis/       experiment configs and result CSVs
docs/         planning notes
```

## Reward gates

| Gate | Weight | Checks |
|---|---|---|
| Format | -0.5 to +0.2 | Patch applies, Python parses, no edits to tests |
| Regression | +0.8 | Functional test suites pass |
| Target / security | +1.5 | Hidden tests that only pass once the bug is fixed |
| Static analysis | +0.5 | Parameterized queries, auth dependencies present |

Every task ships a `gold.patch` (must be solved, normalized score 1.0) and a `noop.patch` (must be
unsolved with a security score of 0). Patches that edit test files score -0.5.

## Quick start

```bash
uv sync
uv run python runtime/validate_tasks.py --sandbox docker --repeat 3
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
5 s statement timeout, no superuser functions). Scoring = fraction of GOAL checks passed minus 0.5
per failed GUARD check (collateral damage such as wrong refunds or leaked PII).

To run a live agent over MCP:

```bash
uv run python runtime/workflows.py start workflows/duplicate_webhook_refunds_101   # prints WORKFLOW_DB_URL + prompt
WORKFLOW_DB_URL=... uv run python runtime/mcp_server.py                            # stdio MCP server
uv run python runtime/workflows.py finish workflows/duplicate_webhook_refunds_101 <db_name>
```

Workflows use the Postgres from `docker compose -f runtime/docker-compose.yml up -d`.

## Prime Intellect environments

Both task families are packaged as [verifiers](https://github.com/PrimeIntellect-ai/verifiers) v1
environments under `environments/`:

| Package | Tasks | Harness | Runtime | `vf-validate` |
|---|---|---|---|---|
| `secops_gym_patches` | 11 patch tasks | bash (agent edits code in a box) | Docker / Prime sandbox | 11/11 valid |
| `secops_gym_workflows` | 5 MCP workflows | tool-only chat | subprocess + Postgres | 5/5 valid |

```bash
uv sync --extra mcp --extra envs              # Linux / macOS / WSL (verifiers is Unix-only)
uv run python scripts/sync_envs.py            # copy tasks + shared code into the packages
sh scripts/build_task_image.sh                # per-rollout box image (~300 MB)
uv run vf-validate secops_gym_patches --runtime.type docker
uv run vf-validate secops_gym_workflows --runtime.type subprocess
```

On Windows, run the same commands inside the Linux devbox: `sh scripts/devbox.sh uv run --no-sync vf-validate ...`.

Publishing: the task image is public at `ghcr.io/zariffromlatif/secops-gym-task:0.1` (rebuild it
with the **publish-task-image** GitHub Action). Push each environment from its folder with the
`prime` CLI (`prime login`, then `prime env push --visibility PRIVATE` from the environment
folder). On Windows, set `PYTHONUTF8=1` first or the CLI crashes printing status symbols.

Hub (private, v0.2.0): `zariffromlatif/secops-gym-patches`, `zariffromlatif/secops-gym-workflows`.

## Sandbox

`--sandbox docker` scores each patch in its own throwaway environment:

- an internal Docker network with **no internet access**
- a fresh Postgres per episode (data on tmpfs)
- the patched app in its own container: read-only filesystem, non-root, all capabilities dropped,
  memory / CPU / process limits
- tests in a separate container that reaches the app over HTTP, so the agent's code never runs
  inside the test process and cannot tamper with results
- hidden tests mounted read-only, only at scoring time
- everything removed afterwards, even on errors

The sandbox image (~290 MB) builds automatically on first use and is rebuilt when
`runtime/Dockerfile.sandbox` or `runtime/requirements-sandbox.txt` changes.

### Local mode

Without `--sandbox docker`, tests import the app in-process against a Postgres on port 5433
(`docker compose -f runtime/docker-compose.yml up -d`). It is faster for writing tasks but not
isolated. Set `DATABASE_URL` to use a different Postgres.
