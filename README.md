# secops-mcp-rlvr-gym

Containerized RLVR (Reinforcement Learning with Verifiable Rewards) environments for training and
evaluating code agents on backend security remediation in FastAPI + PostgreSQL services.

An agent receives a small service with a known security flaw and a bug report, and must return a
patch. The patch is scored by deterministic checks the agent never sees during its rollout, so the
reward cannot be gamed by editing tests or special-casing inputs.

## Status

3 tasks, all validated (gold solved at 1.00, no-op unsolved with zero security score):

| Task | Flaw | CWE |
|---|---|---|
| `invoice_sort_001` | ORDER BY built from raw query params | CWE-89 |
| `invoice_tenant_002` | Invoices readable/editable across tenants | CWE-639 |
| `report_auth_003` | Export endpoint skips authentication | CWE-306 |

## Layout

```
tasks/        one folder per task (app, public tests, hidden checks, gold/noop patches)
verifier/     multi-gate reward function
runtime/      Docker sandbox and episode runner
env/          adapter to the Prime Intellect `verifiers` format
training/     GRPO training and evaluation scripts
thesis/       experiment configs and result CSVs
docs/         planning notes
```

## Reward gates

| Gate | Weight | Checks |
|---|---|---|
| Format | -0.5 to +0.2 | Patch applies, Python parses, no edits to tests |
| Regression | +0.8 | Functional test suites pass |
| Security | +1.5 | Hidden input-validation / isolation tests pass |
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
