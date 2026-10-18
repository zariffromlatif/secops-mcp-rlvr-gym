# secops-gym-patches

Fix a bug in a small FastAPI + PostgreSQL service. There are 7 tasks: 3 security (SQL built from
request params, cross-tenant access, missing authentication) and 4 business-logic (pagination
off-by-one, split rounding, time zones, JOIN double counting).

**How a rollout works**
- Each rollout gets its own container (`secops-gym-task` image) with the service in `/app` and a
  local Postgres. The agent (default: `bash` harness) works as the unprivileged `agent` user.
- At scoring time, hidden tests are written into a root-only directory. The agent's `app/` is
  copied out and served by uvicorn as `nobody`, and **pristine** public tests plus the hidden tests
  run against it over HTTP. Editing tests, or in-process tricks in the app code, can't change the
  result.
- `/app/app` is declared as an artifact, so `--env.id isolated_verifier` can re-score in a fresh box.

**Reward** (0–1). This is the normalized multi-gate score:

| Gate | Points | Check |
|---|---|---|
| format | −0.5 / +0.2 | app code parses, tests untouched |
| regression | up to +0.8 | public + hidden functional tests |
| target | up to +1.5 | hidden tests that only pass once the bug is fixed |
| static | +0.5 | no SQL built from runtime strings |

The per-gate values and `solved` are recorded as metrics.

**Validation** (`vf-validate`, Docker runtime): 7/7 valid. Every gold patch solves its task, and
no untouched task passes (untouched rewards are 0.33–0.50, from regression credit only).

## Run

```bash
# the default image ghcr.io/zariffromlatif/secops-gym-task:0.1 is public; or build it locally:
sh scripts/build_task_image.sh
uv run vf-validate secops_gym_patches --runtime.type docker
uv run vf-eval secops_gym_patches --runtime.type docker -n 7 --model <model>
```

Options: `--env.taskset.categories '["security"]'`, `--env.taskset.image <another tag>`.

Source and task authoring guide: https://github.com/zariffromlatif/secops-mcp-rlvr-gym
