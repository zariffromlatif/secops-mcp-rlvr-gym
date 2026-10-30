# secops-gym-patches

Fix bugs in a small FastAPI + PostgreSQL service. There are 14 tasks: 3 security (SQL built from
request params, cross-tenant access, missing authentication) and 11 business-logic (pagination,
split rounding, time zones, JOIN double counting, shipping quotes, and six harder multi-bug tasks:
proration, inventory reservations, graduated pricing, idempotency keys, loyalty-point expiry, late
fees).

**How a rollout works**
- Each rollout gets its own container (`secops-gym-task` image) with the service in `/app` and a
  local Postgres. The agent (default: `bash` harness) works as the unprivileged `agent` user.
- At scoring time, hidden tests are written into a root-only directory. The agent's `app/` is
  copied out and served by uvicorn as `nobody`, on a port the scorer binds itself, against a fresh
  database through a role that can only read and write rows, and **pristine** public tests plus the
  hidden tests run against it over HTTP, writing their reports to a root-only directory. Editing
  tests or data, processes the agent left running, or in-process tricks in the app code can't
  change the result.
- The scorer (`image/score_box.py`) ships with this package and is copied into the box at scoring
  time, so scorer fixes reach the published image without a rebuild.
- `/app/app` is declared as an artifact, so `--env.id isolated_verifier` can re-score in a fresh box.

**Reward** (0–1). This is the normalized multi-gate score:

| Gate | Points | Check |
|---|---|---|
| format | −0.5 / +0.2 | app code parses, tests untouched |
| regression | up to +0.8 | public + hidden functional tests; read-only endpoints leave stored data unchanged |
| target | up to +1.5 | hidden tests that only pass once the bug is fixed |
| static | +0.5 | no SQL built from runtime strings |

The per-gate values and `solved` are recorded as metrics.

**Validation** (`vf-validate`, Docker runtime): 14/14 valid. Every gold patch solves its task, and
no untouched task passes (untouched rewards are 0.33–0.50: format, regression and static credit,
never target credit).

## Run

```bash
# the default image ghcr.io/zariffromlatif/secops-gym-task:0.1 is public; or build it locally:
sh scripts/build_task_image.sh
uv run vf-validate secops_gym_patches --runtime.type docker
uv run vf-eval secops_gym_patches --runtime.type docker -n 14 --model <model>
```

Options: `--env.taskset.categories '["security"]'`, `--env.taskset.image <another tag>`.

Source and task authoring guide: https://github.com/zariffromlatif/secops-mcp-rlvr-gym
