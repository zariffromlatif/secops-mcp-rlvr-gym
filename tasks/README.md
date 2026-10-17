# Task format

```
tasks/<task_id>/
├── app/            service code the agent can read and edit
├── tests_public/   functional tests the agent can run
├── hidden/         security + regression tests, mounted only at scoring time
├── seed.sql        deterministic database state
├── gold.patch      reference fix, must score ~1.0
├── noop.patch      empty change, must score ~0.0
└── task.yaml       prompt, bug report text, metadata
```

Rules:
- No network access during rollouts.
- `hidden/` is never copied into the agent container.
- CI applies `gold.patch` and `noop.patch` to every task and fails if scores drift.
