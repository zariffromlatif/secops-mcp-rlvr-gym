# Study guide: how the tasks work

Read this top to bottom once, then open each task folder next to it.

## 1. What a "task" is

A task is a tiny, realistic web service with **one bug**, plus everything needed to grade a fix
automatically. A model (or a person) gets the code and a bug report, and must produce a patch.

```
tasks/<task_id>/
├── app/            the service the model can read and edit
│   ├── db.py         database connection (same in every task)
│   └── main.py       the API endpoints, contains the bug
├── tests_public/   tests the model may run (normal behaviour)
├── hidden/         tests the model never sees
│   ├── test_regression_hidden.py   more normal-behaviour checks
│   └── test_target.py / test_security.py   checks that only pass if the bug is fixed
├── seed.sql        the exact database contents for every test run
├── gold.patch      the correct fix (proves the task is solvable)
├── noop.patch      an empty change (proves the hidden tests catch the bug)
└── task.yaml       the bug report shown to the model, and which tests count for what
```

### How a patch is scored

1. Copy `app/`, `tests_public/`, `seed.sql` to a scratch folder and apply the patch. A patch that
   touches anything outside `app/` (tests, seed data) fails the format gate.
2. Copy `hidden/` in **after** the patch, so the patch can't have seen or changed it.
3. Start Postgres and the app in their own containers, with no internet access.
4. Run the tests from a separate container that talks to the app over HTTP.
5. Turn the results into a reward:

| Gate | Points | Question it answers |
|---|---|---|
| Format | -0.5 or +0.2 | Does the patch apply and parse? Did it change only `app/`? |
| Regression | up to +0.8 | Does everything that used to work still work? |
| Target / security | up to +1.5 | Is the bug actually fixed? |
| Static | +0.5 | Is there no SQL built by gluing strings together? |

A fix is **solved** only if every regression and target test passes and the static gate passes
(that is why a fix that is safe but still builds SQL from strings scores 0.83 and is not solved).
The partial points let training see "getting closer" before a model fully solves anything.

### Why two kinds of hidden tests?

- **Regression tests** catch "fixes" that break other things, such as deleting the endpoint. They
  also check that read-only endpoints leave the stored data unchanged, so a "fix" that deletes the
  rows that trigger the bug doesn't count.
- **Target tests** catch the bug itself. `noop.patch` must fail all of them, which is how we
  know they really test the bug.

## 2. The business-logic tasks

### `orders_pagination_004`: off-by-one in page count

**The service:** `GET /orders?page=2&page_size=4` returns orders in pages, plus `total_pages`.

**The bug:** `total_pages = total // page_size`. `//` is integer division and rounds **down**:
9 orders / 4 per page = 2.25, which becomes 2. The 9th order sits on page 3, but the API says
page 3 doesn't exist and returns 404.

**The fix:** round **up**: `math.ceil(total / page_size)`, so 9 / 4 becomes 3.

**How the tests catch it:**
- Public tests only check `total_pages` for a page size that divides evenly (9 / 3) and never ask for
  the last page of an uneven split, so the bug hides there. That's realistic:
  bugs often hide in the "easy" cases.
- Hidden target tests use sizes that don't divide evenly (4, 2, 5, 8) and check that the last page
  is reachable and contains order 9.

**Learn:** integer division, `math.ceil`, and why edge cases (partial pages, empty pages, the
last page) are where bugs live.

### `invoice_split_rounding_005`: losing cents

**The service:** `POST /invoices/2/split {"payers": 3}` splits an invoice amount between payers.

**The bug:** every payer gets `amount // payers`. 10000 cents / 3 = 3333 each, which adds up to
9999. One cent disappears, and in real finance systems that breaks reconciliation.

**The fix:** `divmod(amount, payers)` gives both the base share and the remainder (10000 → 3333,
remainder 1). The first `remainder` payers get one extra cent: `[3334, 3333, 3333]`.

**How the tests catch it:** they check that shares **sum to the total**, differ by at most
1 cent, and that extra cents go to the first payers.

**Why money is stored in cents:** floats can't represent 0.1 exactly (`0.1 + 0.2 != 0.3` in
Python). Integers in cents are exact.

**Learn:** `divmod`, why floats are wrong for money, and "largest remainder" splitting.

### `daily_report_timezone_006`: UTC vs local days

**The service:** `GET /reports/daily?day=2026-03-01&tz=Asia/Dhaka` returns how many invoices were
created on that day, and their total.

**The bug:** the query uses `created_at::date = :day`, which is the **UTC** calendar day. The
`tz` parameter is validated and then ignored. Dhaka is UTC+6, so an invoice created at
00:30 on 1 March in Dhaka (18:30 on 28 February UTC) is counted on the wrong day.

**The fix:**
1. Build local midnight-to-midnight: `datetime.combine(day, time.min, tzinfo=zone)`.
2. Convert both ends to UTC with `.astimezone(timezone.utc)`.
3. Query a range: `created_at >= :start AND created_at < :end`. The end is exclusive, so a row at
   exactly midnight belongs to the next day.

**How the tests catch it:** the seed has invoices placed just before and after Dhaka midnight.
UTC days still have to work (regression); Dhaka days must come out right (target).

**Learn:** UTC storage, `zoneinfo`, half-open ranges `[start, end)`, and why "what day is it?"
depends on where you are.

### `revenue_double_count_007`: a JOIN that duplicates rows

**The service:** `GET /reports/revenue` gives revenue per customer, counting paid invoices that
have at least one payment.

**The bug:** the query JOINs `invoices` to `payments`. A JOIN produces **one row per matching
pair**, so an invoice paid in 3 instalments appears 3 times, and `SUM(amount_cents)` counts it
3 times. Acme's 5000 invoice with 2 payments becomes 10000.

**The fix:** don't JOIN just to check that a payment exists. Use
`EXISTS (SELECT 1 FROM payments p WHERE p.invoice_id = i.id)`, which only answers yes or no and
never duplicates rows.

**How the tests catch it:** customers with only single-payment invoices look correct (public
tests pass), while customers with multi-payment invoices must show the true totals (target).

**Learn:** how JOINs multiply rows, `EXISTS`, and the habit of asking "how many rows does this
JOIN produce?" before aggregating.

## 2b. The harder business-logic tasks (008–011)

These follow one pattern: **the bug report describes one symptom, but the code has two
problems** (010's report adds a vague hint about the second), both covered by rules documented at
the top of `app/main.py`. Public tests pass with both bugs present. To get full marks, the agent has
to read the spec, not just the report.

| Task | Reported symptom | Hidden second problem | What to learn |
|---|---|---|---|
| `subscription_proration_008` | February plan change is wrong | the code assumes 30-day months **and** rounds down instead of half-up | real period length `(end - start).days`, `Decimal.quantize(ROUND_HALF_UP)`, leap years |
| `inventory_reservation_009` | same SKU on two lines oversells | releasing an order twice restores stock twice | aggregate before checking; make operations **idempotent** (`UPDATE ... WHERE status = 'active' RETURNING`) |
| `tiered_pricing_010` | 1,000 units priced wrong | charges every unit at the final tier's price instead of graduated tiers | inclusive vs exclusive bounds; graduated pricing, as on real SaaS pricing pages |
| `idempotency_keys_011` | retry with a changed amount returns the old payment | keys are shared across tenants | the idempotency-key pattern used by Stripe and others; scoping keys per tenant |

In the first evaluation, gpt-oss-120b fixed the reported half of task 009 and missed the
idempotency rule. That's exactly the failure these tasks are designed to catch.

**Tasks 012–014** follow the same pattern. Each was checked against a "naive fix" that repairs
only the reported symptom; that fix still fails part of the target tests.

| Task | Reported symptom | Hidden problems | What to learn |
|---|---|---|---|
| `loyalty_points_expiry_012` | 2024 points still on the balance | redemptions must use the **oldest** points first, so points redeemed before expiry can't expire again; expiry on exactly day 365 | simulating a ledger in time order with a queue (FIFO); why "earned minus redeemed" is not enough once things expire |
| `shipping_quote_013` | a big light box is quoted by its real weight | billable weight rounds **up** to the next 0.5 kg, not to the nearest | volumetric weight; integer ceiling division `-(-a // b)` instead of floats |
| `late_fees_014` | fee charged on the full total of a mostly paid invoice | the 5-day grace period is ignored and the fee has no 5-period cap | counting periods from the end of a grace period; caps; `Decimal` half-up rounding |

## 3. The MCP workflow tasks

These are different from patch tasks. The agent doesn't edit code: it **operates tools**, like
an employee using company software. MCP (Model Context Protocol) is the standard way AI agents
call tools, so these tasks test exactly what agent startups care about.

```
workflows/<id>/
├── seed.sql      the company's data at the start (customers, payments, tickets)
├── task.yaml     the instruction given to the agent, the tools it may use and its max_steps
├── checks.py     hidden checks on the final database (GOAL and GUARD)
├── gold.json     a correct sequence of tool calls (proves it's solvable)
├── noop.json     no tool calls (must score 0)
└── bad_*.json    a careless sequence (must NOT be solved)
```

**The tools** (in `runtime/mcp_tools.py`), of which each workflow offers only those its `task.yaml`
lists: `sql_query` (read-only), `issue_refund`,
`create_ticket`, `close_ticket`, `post_message`.

**Scoring = GOAL minus GUARD penalties:**
- **GOAL checks** ask "did the job get done?" (the right payments refunded, the right tickets
  opened). The reward is the fraction passed, so partial progress counts.
- **GUARD checks** ask "did anything get damaged?" (wrong refunds, customer emails pasted in chat,
  other tickets touched). Each failure costs 0.5. Guards must only detect *damage*: an agent
  that is halfway through must not fail a guard. This was a real bug fixed while building task
  103.

**Why traps matter:** each workflow contains cases that look right but aren't. In 101, a customer
bought the same item twice under *different* webhook ids, which is a real purchase and must not be
refunded. Careless agents fall for these, and that's what makes the task useful for training.

**Safety:** the agent's SQL runs as a restricted database user, in a read-only transaction,
with a 5-second timeout, so it can look at data but not change or break anything. Changes only
happen through the official tools, which check their inputs (you can't refund a failed payment).

**Learn:** SQL `GROUP BY` / `HAVING` (task 102), `EXISTS` (task 101), date ranges (102, 103),
and thinking about edge cases before acting.

**Harder workflows:**
- `q1_vip_escalation_104` combines an aggregation with a filter and an ordering. The traps:
  - refunded or failed payments counted as spend;
  - payments just outside the quarter (31 Dec 23:50, 1 Apr 00:10);
  - a big spender with only closed tickets;
  - "invoice copy needed" vs "Invoice copy needed", which are not duplicates.
- `refund_policy_v2_105` stacks five policy rules, including "at most one refund per customer
  per batch" (refund the newest payment, deny the rest).
- `ledger_reconciliation_106` is a **report-only** job: compare payments with ledger credits and
  open a ticket per mismatch, without moving money. The traps:
  - a payment refunded in two partial credits that add up correctly (not a mismatch);
  - a credit recorded twice (the total is wrong even though each row looks fine);
  - a mismatch that already has an open ticket (count it, but don't open another);
  - the `issue_refund` tool is available, and "fixing" the ledger with it is damage.
- `cancellation_refunds_107` gives tickets **without** a linked payment, so the agent must find
  the right one. The traps:
  - the customer's latest payment failed (refund their latest *succeeded* one);
  - a payment at exactly 2026-03-31 00:00 (eligible) and one at 23:59:59 the day before (not);
  - ticket text asking for more than the policy allows ("refund all my payments", "also refund
    my brother's payment"). The agent must follow the policy, not the customer's request.

**A lesson from building them:** our first version didn't say that status values are lowercase.
A model searched for `'OPEN'`, found nothing, and failed for a reason that had nothing to do with
reasoning. A good task tests a skill, not a hidden convention. When a model fails, check whether
the task was fair before blaming the model.

## 4. The security tasks (written earlier)

- **`invoice_sort_001`:** the sort column from the URL was pasted directly into SQL text. The fix
  only allows a fixed list of column names and builds the query with SQLAlchemy expressions.
  Learn: never put user input into SQL text; use allow-lists and bound parameters.
- **`invoice_tenant_002`:** invoices were looked up by id only, so one company could read or edit
  another company's invoices. The fix adds `AND tenant_id = :tenant` and returns 404 for other
  tenants' rows. Learn: every query in a multi-tenant app must filter by tenant.
- **`report_auth_003`:** one endpoint forgot the authentication dependency and trusted a
  `tenant_id` from the URL. The fix adds `Depends(require_tenant)` and takes the tenant from the
  API key. Learn: identity must come from authentication, never from user-supplied parameters.

For the background, work through the matching free labs in **PortSwigger Web Security Academy**
(SQL injection, Access control, Authentication).

## 5. How to write your own task

**Write the correct version first, then break it.** It's much easier than starting from buggy code.

1. **Copy a similar task:** `cp -r tasks/orders_pagination_004 tasks/my_task_015`, then rename
   the `id` in `task.yaml`.
2. **Change the story:** a different domain (clinic appointments, bus tickets, library loans) and
   1–2 endpoints. Keep it small.
3. **Write the correct `app/main.py`.** Save a copy as `gold_main.py` outside `tasks/`.
4. **Write tests against the correct version:**
   - `tests_public/`: normal behaviour that also works with the bug present
   - `hidden/test_regression_hidden.py`: more normal behaviour
   - `hidden/test_target.py`: behaviour that only the correct version has
5. **Introduce one realistic bug** into `app/main.py`, the kind a rushed developer would write.
6. **Make the patches:**
   ```bash
   diff -u --label a/app/main.py --label b/app/main.py tasks/my_task_015/app/main.py gold_main.py > tasks/my_task_015/gold.patch
   ```
   `noop.patch` stays empty.
7. **Write the bug report** in `task.yaml` the way a user would describe the symptom. Describe
   what goes wrong, not how to fix it.
8. **Validate:**
   ```bash
   uv run python runtime/validate_tasks.py --sandbox docker --repeat 3
   ```
   Your task is ready when it shows `PASS`, gold = 1.00 and noop with zero target score. If noop
   still passes some target test, that test doesn't really detect the bug (this happened while
   building task 005: "shares differ by at most 1 cent" passes when all shares are equal).

## 6. Free learning path, in order

1. **Python basics:** functions, lists, dicts, `divmod`, exceptions. Use the official Python tutorial.
2. **SQL:** SQLBolt (interactive), then JOINs and `GROUP BY` in the PostgreSQL tutorial.
3. **FastAPI:** the official tutorial, "First steps" through "Dependencies".
4. **pytest:** the "Get started" page plus fixtures and `parametrize`. Read the tests in this repo.
5. **git and diff:** create and apply a patch by hand once.
6. **Security:** PortSwigger Web Security Academy, the free labs.

At 1–2 hours a day, steps 1–4 take about 2–3 weeks. Read one task folder alongside each step.
