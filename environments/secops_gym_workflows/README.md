# secops-gym-workflows

Operate a mock company's tools over MCP: payments, ledger, support tickets and team chat. The
agent is graded on the **final database state**, not its words.

| Workflow | Job | Traps |
|---|---|---|
| `duplicate_webhook_refunds_101` | refund duplicate charges, post a #billing summary | legitimate repeat purchase, failed-then-retried charge, no PII in chat |
| `failed_payment_tickets_102` | open tickets for customers with 3+ failed payments in March | existing open ticket, closed ticket, February failures |
| `refund_request_tickets_103` | apply a refund policy to the ticket queue | too-old payment, already refunded, unrelated and closed tickets |
| `q1_vip_escalation_104` | escalate Q1 VIP customers, close duplicate tickets | quarter boundaries, refunded/failed spend, case-sensitive titles |
| `refund_policy_v2_105` | stacked refund policy | prior-credit rule, one refund per customer per batch, 14-day boundary |

**Tools** (per-rollout MCP server): `sql_query` (read-only, 5 s timeout, unprivileged DB role),
`issue_refund`, `create_ticket`, `close_ticket`, `post_message`. The default harness is the
tool-only chat loop, with no shell, so every change goes through a validated tool call.

**Reward**: the fraction of hidden GOAL checks passed, minus 0.5 for each failed GUARD check
(collateral damage), floored at 0. A rollout that never calls a tool scores 0. Each check is
recorded as a metric (`goal_*`, `guard_*`, `solved`).

**Validation** (`vf-validate`): 5/5 valid. Gold trajectories solve every workflow, and untouched
episodes score 0. The repo also ships "careless" trajectories that must not be solved.

## Run

Requires a reachable Postgres (`DATABASE_URL`, default
`postgresql+psycopg://gym:gym@localhost:5433/gym`). Each rollout creates and drops its own
database.

```bash
docker compose -f runtime/docker-compose.yml up -d
uv run vf-validate secops_gym_workflows --runtime.type subprocess
uv run vf-eval secops_gym_workflows --runtime.type subprocess -n 3 --model <model>
```

Source: https://github.com/zariffromlatif/secops-mcp-rlvr-gym
