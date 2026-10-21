# First model evaluations (2026-10-20/21)

Real agents attempted every task through the Prime Intellect verifiers v1 environments.

**Setup**
- `vf-eval` (verifiers 0.4.0).
- Patch tasks use the bash harness. The agent edits code inside the task container and is scored
  by the in-box scorer.
- Workflows use the tool-only harness, with MCP tools only.
- Models are served through Groq's free tier, behind `scripts/llm_proxy.py`, which retries rate
  limits and strips the `channel` field Groq rejects.
- 1 attempt per task. Qwen's timezone task had 3 attempts. Default sampling.

## Results

| Task | Category | Qwen3.8-27B | gpt-oss-120b |
|---|---|---|---|
| `invoice_sort_001` | security | **0.83, not solved** (static gate) | **0.83, not solved** (static gate) |
| `invoice_tenant_002` | security | ✅ 1.00 | — (provider: request too large) |
| `report_auth_003` | security | ✅ 1.00 | — (provider: daily quota) |
| `orders_pagination_004` | business logic | ✅ 1.00 | — (provider: daily quota) |
| `invoice_split_rounding_005` | business logic | ✅ 1.00 | ✅ 1.00 |
| `daily_report_timezone_006` | business logic | ✅ 1.00 (3/3) | ✅ 1.00 |
| `revenue_double_count_007` | business logic | ✅ 1.00 | — (provider: daily quota) |
| `duplicate_webhook_refunds_101` | MCP workflow | ✅ 1.00 | not run (daily quota) |
| `failed_payment_tickets_102` | MCP workflow | ✅ 1.00 | not run (daily quota) |
| `refund_request_tickets_103` | MCP workflow | ✅ 1.00 | not run (daily quota) |
| **Solved** | | **9 / 10** (mean reward 0.98) | **2 / 3** completed attempts |

"—" means the provider refused the request (free-tier limits), not that the model failed. Those
attempts are excluded rather than counted as failures. The per-run tables with gate scores are in
this folder, and the raw traces are in `traces/`.

## Findings

1. **The static gate catches what tests miss.** On `invoice_sort_001`, both models added an
   allow-list check, so the hidden security tests pass and the endpoint is safe in practice. But
   both kept building SQL with an f-string, which the task explicitly forbids. With tests alone,
   this would count as solved. Only the AST gate tells "safe by validation" apart from "safe by
   construction". This is the core argument of the paper (multi-signal deterministic verifiers vs
   test-only or LLM-judge rewards).
2. **Most tasks are too easy for a 27B model.** For GRPO, a task the model always solves gives zero
   advantage, so no learning signal. The next tasks should be harder: multi-file changes, subtler
   bugs, fewer hints in the bug report. Today only `invoice_sort_001` discriminates.
3. **The workflow traps did not catch Qwen.** It refunded only true duplicates, skipped customers
   with existing open tickets, and applied the refund policy correctly. Harder traps are needed to
   separate stronger models.
4. **Free-tier limits shape what can be measured.** Groq allows 8K tokens per minute and 200K
   tokens per day per model, and one patch episode costs 25–35K tokens. Proper solve rates
   (≥ 3 attempts per task) need several days of quota, or a paid or local endpoint.

## Round 2: harder tasks (2026-10-21)

These tasks were built so that one fix is not enough. Each has several interacting rules, a bug
report that names only one symptom, and public tests that pass with the bug still present.

| Task | Qwen3.8-27B | gpt-oss-120b |
|---|---|---|
| `subscription_proration_008` | — (provider limits) | ✅ 1.00 |
| `inventory_reservation_009` | — (provider limits) | **0.75, not solved**: fixed the reported oversell, never made `release` idempotent |
| `tiered_pricing_010` | — (provider limits) | ✅ 1.00 |
| `idempotency_keys_011` | ✅ 1.00 | ✅ 1.00 |
| `q1_vip_escalation_104` | not run (quota) | ✅ 1.00, every trap avoided |
| `refund_policy_v2_105` | not run (quota) | 0.00, **excluded** (see below) |

**What this shows**
- `inventory_reservation_009` works as designed. The model fixed exactly what the bug report
  described and ignored the second documented rule. "Read the whole spec" is a real, trainable gap.
- Most harder tasks are still solved by gpt-oss-120b, so more discriminating tasks are needed.
  The useful ones so far are `invoice_sort_001` (static gate) and `inventory_reservation_009`
  (partial fix).
- **A fairness bug, found and fixed.** On `refund_policy_v2_105`, gpt-oss-120b filtered
  `status = 'OPEN'` (the prompt wrote OPEN in capitals), got 0 rows, and reported 0 requests. The
  tool description never listed the stored values, so this measured a hidden convention, not
  reasoning. The `sql_query` description now documents the lowercase status values. This attempt
  is excluded and must be re-run.
- Groq's free tier limits are a **rolling 24-hour window**, not a daily reset. Qwen's attempts
  failed on quota even after a small test request succeeded.

## First verifier-audit data (2026-10-21)

The 5 workflow solutions above were re-scored with V1, V3 and an LLM judge (V4, gpt-oss-20b).
See `results/audit/verdicts.csv`. Patch solutions from these runs can't be re-scored, because
they predate the environment saving final code (0.2.1).

- **Judge false positive on `refund_policy_v2_105`.** The agent processed 0 requests (a wrong-case
  status filter). The judge accepted "no eligible tickets were found" without checking; V3
  correctly failed it.
- **A methodology lesson.** A first judge run truncated tool results to 800 characters, and that
  produced two spurious judge errors (e.g. payment 17 sat beyond the cut). Judges and annotators
  now see the full results the agent saw. The paper must document how judge inputs are built.

## Reproduce

```bash
sh scripts/run_eval.sh patches   qwen/qwen3.8-27b -r 1
sh scripts/run_eval.sh workflows qwen/qwen3.8-27b -r 1
uv run python scripts/summarize_evals.py .tmp/evals/<run-dir>
```
