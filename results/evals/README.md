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
Those verdicts are in `results/audit/verdicts.csv` as of commit `92fe896` (Round 3 below replaced
the file); the judge's answers are still in `results/audit/judge_cache.jsonl`. Patch solutions from
these runs can't be re-scored, because they predate the environment saving final code (0.2.1).

- **Judge false positive on `refund_policy_v2_105`.** The agent processed 0 requests (a wrong-case
  status filter). The judge accepted "no eligible tickets were found" without checking; V3
  correctly failed it.
- **A methodology lesson.** A first judge run truncated tool results to 800 characters, and that
  produced two spurious judge errors (e.g. payment 17 sat beyond the cut). Judges and annotators
  now see the full results the agent saw. The paper must document how judge inputs are built.

## Round 3: multi-day campaign (2026-10-22 to 2026-10-25)

All 16 tasks of that time (11 patch, 5 workflows) for both models, 1 attempt each, spread over 4 days of
Groq's free-tier quota (`scripts/eval_campaign.sh`). 31 of 32 attempts finished. gpt-oss-120b's
`tiered_pricing_010` exceeded Groq's per-request size limit on every try and is excluded.
Every solution was re-scored with V1 (public tests), V2 (+ hidden tests), V3 (+ static and
anti-tamper checks; for workflows, goal + guard) and V4 (LLM judge, gpt-oss-20b).

| Model | Patch tasks solved (V3) | Workflows solved (V3) |
|---|---|---|
| Qwen3.8-27B | 9 / 11 | 4 / 5 |
| gpt-oss-120b | 10 / 10 | 5 / 5 |

**Where the verifiers disagree** (`results/audit/verdicts.csv`):

| Task | Model | V1 | V2 | V3 | V4 | What happened |
|---|---|---|---|---|---|---|
| `invoice_tenant_002` | Qwen | pass | fail | fail | fail | The fix stopped saving updates. Public tests alone (V1) pass it: a test-only false positive. |
| `invoice_sort_001` | Qwen | pass | pass | fail | fail | Safe by allow-list, but SQL is still built with an f-string. Tests can't see it. |
| `daily_report_timezone_006` | gpt-oss | pass | pass | pass | fail | Judge claims `datetime.combine` has no `tzinfo` argument; it has since Python 3.6. Likely judge false negative. |
| `invoice_tenant_002` | gpt-oss | pass | pass | pass | fail | Judge guesses a rollback "may raise"; the hidden cross-tenant tests pass. Likely judge false negative. |
| `inventory_reservation_009` | Qwen | pass | pass | pass | fail | Judge objects to aggregating duplicate lines, which the spec requires. Likely judge false negative. |

"Likely" until the blind human labels are in. A methodology note: the judge first returned no
verdict on 7 of 20 solutions, because gpt-oss-20b spent its whole default reply budget on hidden
reasoning. The judge now sizes the budget to the provider's request limit and retries once with
low reasoning effort (see `audit/judge.py`).

## Scorer fixes after the campaign (v0.3.0, 2026-10-30)

A review of the scorers found ways to earn reward without a real fix. Each is fixed and tested:

- **Seed data could be edited.** `runtime/score_patch.py` applied a patch's edits to `seed.sql` and
  gave the edited seed to the tests, so a patch that only merged the multi-payment rows scored 1.0
  on `revenue_double_count_007` with the bug unfixed. It also read touched paths relative to the
  repo instead of the task, so the format gate's syntax check never saw the patched files. Patches
  may now touch only `app/`. The Prime environment and the audit always used the original seed.
- **The app could rewrite its own test reports.** In the Prime environment the app ran during the
  tests while JUnit reports were written to `/tmp`; app code that rewrote them scored full marks
  with the bug unfixed, and a leftover agent process could take the app's port. The in-box scorer
  now stops the agent's processes, keeps reports in a root-only directory, and serves the app
  against a fresh database through a role that can only read and write rows. In the Docker
  sandbox, the app no longer connects as a Postgres superuser.
- **The static gate only saw inline SQL.** Moving the f-string into a variable passed it. It now
  follows variables, `+=` and `.join`, and no longer flags `"..." + "..."` of two literals.
- **Stored data was never checked.** A revenue endpoint that deleted the extra payment rows passed
  every test. Hidden regression tests now check that read-only endpoints leave the data unchanged.
- **`subscription_proration_008` had no exact half cent,** so `round()` (half to even) passed. A
  new target test covers 500.5 -> 501.
- **Workflow tool lists and `max_steps` were not enforced:** every workflow exposed all five tools.
  Each now offers only the tools its `task.yaml` lists.

None of this changes the results above. No solution in `results/audit/solutions.jsonl` uses these
tricks; re-scoring all 20 patch solutions with the v0.3.0 tests and gates gives the same V1-V3
verdicts; and no workflow solution called a tool outside its task's list or went past `max_steps`.

## Reproduce

```bash
sh scripts/run_eval.sh patches   qwen/qwen3.8-27b -r 1
sh scripts/run_eval.sh workflows qwen/qwen3.8-27b -r 1
uv run python scripts/summarize_evals.py .tmp/evals/<run-dir>
```
