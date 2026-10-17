# secops-mcp-rlvr-gym

Containerized RLVR (Reinforcement Learning with Verifiable Rewards) environments for training and
evaluating code agents on backend security remediation in FastAPI + PostgreSQL services.

An agent receives a small service with a known security flaw and a bug report, and must return a
patch. The patch is scored by deterministic checks the agent never sees during its rollout, so the
reward cannot be gamed by editing tests or special-casing inputs.

## Status

1 task (`invoice_sort_001`). Gold patch scores 1.00, no-op patch 0.33 (unsolved).

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
docker compose -f runtime/docker-compose.yml up -d
uv run python runtime/validate_tasks.py
uv run python runtime/score_patch.py tasks/invoice_sort_001 path/to/your.patch
```

Set `DATABASE_URL` to point at a different Postgres.
