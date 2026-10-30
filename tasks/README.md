# Task format

```
tasks/<task_id>/
├── app/            service code the agent can read and edit
├── tests_public/   functional tests the agent can run
├── hidden/         regression tests plus target (security tasks: security) tests, mounted only at scoring time
├── seed.sql        deterministic database state
├── gold.patch      reference fix, must be solved (score 1.0)
├── noop.patch      empty change, must stay unsolved with a target score of 0
└── task.yaml       prompt, bug report text, metadata, editable paths, scoring groups
```

Rules:
- No network access during rollouts.
- `hidden/` is never copied into the agent container.
- A patch may only touch the task's `editable_paths` (`app/`); editing tests or seed data scores -0.5.
- `noop.patch` still earns format, regression and static credit (0.33-0.50), never target credit.
- CI applies `gold.patch` and `noop.patch` to every task, three times each, and fails if scores drift.
