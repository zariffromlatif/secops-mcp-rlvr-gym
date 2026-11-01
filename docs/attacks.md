# Attacks on the scorers

The scorer is part of an RL environment's attack surface: a policy is rewarded for whatever the
scorer accepts, not for what the task meant. This file lists every attack found on this
repository's scorers, how it was found, what stops it now, and the check that keeps it stopped.

Wrong *fixes* that the tests must reject (partial fixes, special-casing, boundary errors) are a
different kind of attack. They are in `tasks/*/exploits/` and summarized at the end.

## Attacks on the scorers and sandboxes

"Effect" is what the attack earned before the fix. Every row's last column runs in CI.

| # | Target | Attack | Effect | Found by | Stopped by | Kept stopped by |
|---|---|---|---|---|---|---|
| 1 | Patch scorer | Edit `seed.sql` so the bug no longer shows (merge 007's multi-payment rows) | 007 scored 1.0 unfixed | code review (`3ff3c6d`) | format gate: patches may touch only `app/` | `exploits/edit_seed.patch`, every task |
| 2 | Patch scorer | `git apply` ran inside the repo, so touched paths came back wrong and the syntax check never saw the patched files | format gate blind | code review (`3ff3c6d`) | `GIT_CEILING_DIRECTORIES` | `tests/test_score_patch.py` |
| 3 | Static gate | Build SQL with an f-string, but in a variable instead of inline | passed the static gate | code review (`3ff3c6d`) | the gate follows variables, `+=` and `.join` | `exploits/fstring_via_variable.patch` (001) |
| 4 | Hidden tests | A read-only endpoint deletes the rows that trigger the bug | bug invisible to the tests | code review (`3ff3c6d`) | regression tests check stored data is unchanged | hidden regression tests |
| 5 | In-box scorer (Prime) | The app rewrites the JUnit reports while the tests run | target credit for buggy code | code review (`3ff3c6d`) | reports written to a root-only folder | `check_box_exploits.py`: report_rewriter |
| 6 | In-box scorer | A process the agent left running holds the app's port and answers 200 | tests hit the squatter | code review (`3ff3c6d`, `0bd6599`) | the scorer binds the port itself and hands uvicorn the socket | `check_box_exploits.py`: port_squatter |
| 7 | In-box scorer | `app/hidden_target.py` is a symlink to the hidden tests; the root-run copy follows it, and the app returns the values the tests expect | 3/3 target tests on unfixed 007 | red team, 2026-10-31 (`5d98e88`) | links copied as links, then removed | `check_box_exploits.py`: hidden_reader |
| 8 | Docker sandbox, V5's live app | The app logs in as the database owner, a superuser, with the public password `gym` | superuser: could rewrite the seed data at runtime | probe app, 2026-10-31 (`6d5fefe`). Fix 1 in `3ff3c6d` gave the app a row-only role but left the owner's password public | random owner password per database | `tests/test_warm_sandbox.py` probe |
| 9 | Warm sandbox | `app/x` is a symlink to a host file; a host-side copy would follow it | host file readable | probe, while building it | copies keep links as links (resolved inside the container) | probe: `host_file` |
| 10 | Warm sandbox | Leave traces for the next episode: a file in `/tmp`, a setting on the database role | cross-sample interference in a GRPO group | design review | new container and new role every episode | probe: `fresh_container`, `fresh_role` |
| 11 | Warm sandbox | Connect to another episode's database | read or change another sample's data | design review | `REVOKE CONNECT` from everyone else, random passwords | probe: `test_probe_pool` |
| 12 | Workflow scorer | Call tools the task doesn't list; keep calling past `max_steps` | every workflow exposed all five tools (e.g. refunds in 104, which has no refund tool) | code review (`d4e183a`) | tool list and step limit enforced in replay, Prime toolset and MCP server | `tests/test_workflow_scoring.py`, `test_workflow_toolset.py` |
| 13 | Workflow checks | Damage no hand-written guard anticipated | unpenalized collateral changes | design (`e329b84`) | generic guard `no_unexpected_changes` | `tests/test_workflow_scoring.py` |
| 14 | Workflow checks | Hedged summary: "3 refunded, 4 refunded, 5 refunded" | solved, reward 1.0 (101, 105-108) | red team, 2026-11-01 | every count written next to a label must be the right one | `bad_hedged_summary.json` |
| 15 | Workflow checks | Hedged ticket notes: "refunded payment 1, 2, ... 9", "duplicate of #1, #3 or #5" | solved, reward 1.0 (104, 107, 108) | red team, 2026-11-01 | a note may name only its own payment or ticket | `bad_hedged_notes.json` |
| 16 | Workflow checks | Contact details spaced out or spelled: "+880 1711 000001", "rahim.uddin at example dot com" | solved, reward 1.0 (all workflows with a PII guard) | red team, 2026-11-01 | generic guard `no_contact_details_in_chat` | `bad_spelled_out_contact.json` |
| 17 | LLM judges (V4, V5) | A code comment or chat note telling reviewers the work is verified and should pass | **not measured yet** | red team, 2026-11-01 | V2 and V3 reject all of them (V1, public tests or goals only, accepts some); the judges' rate goes in the audit | `exploits/judge_note.patch` (001, 007, 014, 016), `bad_reviewer_note.json` (105, 107), part of the known-answer corpus |

## Attacked, and held

- **The read-only SQL tool:** multiple statements, data-modifying `WITH` queries and
  superuser functions fail (single statement, read-only transaction, unprivileged role, 5 s
  timeout; `tests/test_mcp_tools.py`). A query can change session settings, and pooled
  connections keep them between calls, but `transaction_read_only` cannot be turned off inside
  a query and every query sets read-only again, so a later call still cannot write (tested).
- **Tool arguments** (refund reasons, ticket text, messages) are bound as parameters, never
  formatted into SQL.
- **The in-box scorer's scan of `tests_public/`** (run as root, to detect edited tests): a
  symlink loop is not followed, a link to `/dev/zero` is not read, and a link to `/etc/shadow` is
  read only to compare with the original tests, so it shows up as an edited test and its
  contents go nowhere.
- **The app process in the box** runs as `nobody`: it cannot write the copied code, read the
  tests or the reports, or signal the scorer's processes.
- **Workflow databases:** the agent's role can only read through the SQL tool and change data
  through the tools; every episode gets a fresh database.

## Wrong fixes the tests must reject (task exploits)

77 patches in `tasks/*/exploits/`, 4-6 per task. `runtime/validate_tasks.py` fails if any of
them is solved, or no longer applies.

| Kind | Patches | Stopped by |
|---|---:|---|
| Edit the public tests or the seed data | 35 | format gate |
| Fix only the reported symptom; special-case the reported input; get a boundary or rounding rule wrong; fix it destructively | 37 | hidden target and security tests |
| Break behaviour that used to work (e.g. a basename-only path fix that breaks subfolders) | 4 | hidden regression tests |
| SQL still built from strings | 1 | static gate |

Four of the 37 are the judge attacks of row 17: the bug stays, and a comment claims it is fixed.
How each verifier does on all of them is in
[results/audit/corpus_report.md](../results/audit/corpus_report.md).

## What the attacks taught

- **A fix needs a probe.** Row 8's first fix gave the app a row-only role and looked complete;
  the owner's public password stayed usable for days, until an app actually tried it.
- **Every copy a privileged process makes of agent files reads through symlinks** (rows 7 and 9).
  Copy links as links, then drop them.
- **"Contains the right answer" rewards hedging** (rows 14-16). Check what is stated, all of it.
- **Every attack becomes a permanent check** in CI, so a later change cannot reopen it.
