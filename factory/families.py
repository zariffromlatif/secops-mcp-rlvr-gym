"""Task families: each builds one task from a random generator, as {relative path: file content}.

A family fixes the bug and the shape of the service; the generator varies the business domain,
names, the seed data and the parameters. Expected test values come from a reference
implementation in this module, on inputs chosen so that the original bug fails every target test
(and the gold fix passes all of them), which the factory checks by validating each task.
"""

from __future__ import annotations

import difflib
import math
import random
from textwrap import dedent

from factory.common import CONFTEST, DB_PY, STORED_DATA, sql_values

PEOPLE = ["Acme Ltd", "Bolt Traders", "Cedar Foods", "Delta Print", "Echo Labs", "Falcon Air", "Grove Cafe",
          "Harbor Steel", "Iris Health", "Juniper Bank", "Kestrel Media", "Lumen Labs", "Meghna Traders",
          "Nimbus Cloud", "Orchid Spa", "Padma Foods", "Quartz Retail", "Rupsha Tea", "Surma Textiles",
          "Teesta Motors", "Umbra Games", "Vista Optics", "Willow Farms", "Xenon Power", "Yarn Works"]


def _diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "a/app/main.py", "b/app/main.py"))


def _task_yaml(task_id: str, family: str, category: str, prompt: str, group: str, cwe: str = "") -> str:
    target = "security: [hidden/test_security.py]" if group == "security" else "target: [hidden/test_target.py]"
    return (f"id: {task_id}\ncategory: {category}\n" + (f"cwe: {cwe}\n" if cwe else "") +
            f"family: {family}\ngenerated: true\ndifficulty: easy\neditable_paths:\n  - app/\nprompt: |\n" +
            "".join(f"  {line}\n" if line else "\n" for line in prompt.strip().splitlines()) +
            f"scoring:\n  regression: [tests_public, hidden/test_regression_hidden.py]\n  {target}\n")


def _files(task_id, family, category, prompt, group, buggy, fixed, seed, helpers, public, regression, target,
           cwe="", per_test_seed=False) -> dict[str, str]:
    conftest = CONFTEST.replace("@pytest.fixture(scope=\"session\", autouse=True)",
                                "@pytest.fixture(autouse=True)") if per_test_seed else CONFTEST
    hidden_target = "hidden/test_security.py" if group == "security" else "hidden/test_target.py"
    return {
        "task.yaml": _task_yaml(task_id, family, category, prompt, group, cwe),
        "app/__init__.py": "",
        "app/db.py": DB_PY,
        "app/main.py": buggy,
        "seed.sql": seed,
        "tests_public/conftest.py": conftest + helpers,
        "tests_public/test_public.py": public,
        "hidden/conftest.py": conftest + helpers + STORED_DATA,
        "hidden/test_regression_hidden.py": regression,
        hidden_target: target,
        "gold.patch": _diff(buggy, fixed),
        "noop.patch": "",
    }


# ---------------------------------------------------------------- pagination: total_pages rounds down
SKINS_PAGES = [("orders", "customer", "total_cents"), ("invoices", "customer", "amount_cents"),
               ("shipments", "recipient", "weight_g"), ("bookings", "guest", "nights"), ("tickets", "requester", "priority")]


def pagination(rng: random.Random, task_id: str) -> dict[str, str]:
    table, who, number = rng.choice(SKINS_PAGES)
    total = rng.randint(7, 23)
    default = rng.choice([s for s in range(3, 9) if total % s and s < total])
    divisor = next(d for d in range(2, total + 1) if total % d == 0)
    uneven = [s for s in range(2, total) if total % s][:4]
    rows = [(rng.choice(PEOPLE), rng.randint(1, 50000)) for _ in range(total)]
    pages = lambda size: math.ceil(total / size)  # noqa: E731  the reference

    buggy = dedent(f'''\
        from fastapi import Depends, FastAPI, HTTPException, Query
        from sqlalchemy import text

        from app.db import get_db

        app = FastAPI(title="{table.title()}")


        @app.get("/{table}")
        def list_{table}(
            page: int = Query(1, ge=1),
            page_size: int = Query({default}, ge=1, le=50),
            db=Depends(get_db),
        ):
            total = db.execute(text("SELECT COUNT(*) FROM {table}")).scalar_one()
            total_pages = max(1, total // page_size)
            if page > total_pages:
                raise HTTPException(status_code=404, detail="Page out of range")

            rows = db.execute(
                text("SELECT id, {who}, {number} FROM {table} ORDER BY id LIMIT :limit OFFSET :offset"),
                {{"limit": page_size, "offset": (page - 1) * page_size}},
            ).mappings().all()
            return {{
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "items": [dict(r) for r in rows],
            }}
        ''')
    fixed = buggy.replace("from fastapi import", "import math\n\nfrom fastapi import", 1).replace(
        "total_pages = max(1, total // page_size)", "total_pages = max(1, math.ceil(total / page_size))")
    seed = (f"DROP TABLE IF EXISTS {table} CASCADE;\n\nCREATE TABLE {table} (\n    id SERIAL PRIMARY KEY,\n"
            f"    {who} TEXT NOT NULL,\n    {number} INTEGER NOT NULL\n);\n\n"
            f"INSERT INTO {table} ({who}, {number}) VALUES\n{sql_values(rows)};\n")
    helpers = f'''

def ids(response):
    return [item["id"] for item in response.json()["items"]]


def get(client, **params):
    return client.get("/{table}", params=params)
'''
    first = list(range(1, default + 1))
    public = dedent(f'''\
        from conftest import get, ids


        def test_first_page(client):
            r = get(client)
            assert r.status_code == 200
            assert ids(r) == {first}
            assert r.json()["total"] == {total}


        def test_exact_division(client):
            assert get(client, page_size={divisor}).json()["total_pages"] == {total // divisor}


        def test_page_zero_rejected(client):
            assert get(client, page=0).status_code == 422
        ''')
    regression = dedent(f'''\
        from conftest import get, ids, seed, stored_data


        def test_single_big_page(client):
            r = get(client, page_size=50)
            assert ids(r) == list(range(1, {total + 1}))
            assert r.json()["total_pages"] == 1


        def test_page_far_past_end_is_404(client):
            assert get(client, page={total + 1}, page_size=1).status_code == 404


        def test_page_size_bounds(client):
            assert get(client, page_size=1).json()["total_pages"] == {total}
            assert get(client, page_size=0).status_code == 422
            assert get(client, page_size=51).status_code == 422


        def test_items_have_expected_fields(client):
            assert set(get(client).json()["items"][0]) == {{"id", "{who}", "{number}"}}


        def test_listing_changes_no_stored_data(client):
            seed()
            before = stored_data()
            get(client, page=2)
            assert stored_data() == before
        ''')
    cases = [(s, pages(s)) for s in uneven]
    target = dedent(f'''\
        """The last, partially filled page must exist and be reachable."""

        import pytest

        from conftest import get, ids


        @pytest.mark.parametrize("page_size,pages", {cases})
        def test_total_pages_rounds_up(client, page_size, pages):
            assert get(client, page_size=page_size).json()["total_pages"] == pages


        @pytest.mark.parametrize("page_size,page", {cases})
        def test_last_partial_page_reachable(client, page_size, page):
            r = get(client, page=page, page_size=page_size)
            assert r.status_code == 200
            assert ids(r)[-1] == {total}
        ''')
    prompt = f'''
You are working on a small FastAPI service that lists {table} from PostgreSQL.

Bug report: "With {total} {table} and the default page size of {default}, the API says there are only
{total // default} pages and page {total // default + 1} returns 404, so the last {table} never show up."

Fix GET /{table} so that:
- total_pages counts a final, partially filled page
- every row is reachable on some page
- pages past the end still return 404, and existing behaviour is otherwise unchanged

You may run the tests in tests_public/. Do not modify test files.
'''
    return _files(task_id, "pagination", "business-logic", prompt, "target", buggy, fixed, seed, helpers,
                  public, regression, target)


# ---------------------------------------------------------------- split: shares lose leftover cents
SKINS_SPLIT = [("invoices", "invoice"), ("bills", "bill"), ("orders", "order"), ("bookings", "booking")]


def split_rounding(rng: random.Random, task_id: str) -> dict[str, str]:
    table, noun = rng.choice(SKINS_SPLIT)
    amounts = [rng.randint(100, 60000) for _ in range(rng.randint(4, 6))]
    amounts[0] = rng.randint(10, 600) * 12          # splits evenly 2, 3, 4 and 6 ways
    amounts[1] = rng.randint(30, 3000) * 3 + 1      # leaves 1 cent over 3 ways
    amounts[2] = rng.randint(1, 4) * 7 + rng.randint(2, 6)  # a small amount with a remainder of 2-6 over 7
    rows = [(rng.choice(PEOPLE), a) for a in amounts]

    def shares(amount, payers):  # the reference
        base, remainder = divmod(amount, payers)
        return [base + 1 if i < remainder else base for i in range(payers)]

    buggy = dedent(f'''\
        from fastapi import Depends, FastAPI, HTTPException
        from pydantic import BaseModel, Field
        from sqlalchemy import text

        from app.db import get_db

        app = FastAPI(title="{noun.title()} splitting")


        class SplitRequest(BaseModel):
            payers: int = Field(ge=1, le=20)


        @app.post("/{table}/{{{noun}_id}}/split")
        def split_{noun}({noun}_id: int, body: SplitRequest, db=Depends(get_db)):
            amount = db.execute(
                text("SELECT amount_cents FROM {table} WHERE id = :id"), {{"id": {noun}_id}}
            ).scalar()
            if amount is None:
                raise HTTPException(status_code=404, detail="{noun.title()} not found")

            share = amount // body.payers
            shares = [share] * body.payers
            return {{"{noun}_id": {noun}_id, "amount_cents": amount, "shares": shares}}
        ''')
    fixed = buggy.replace(
        "    share = amount // body.payers\n    shares = [share] * body.payers\n",
        "    base, remainder = divmod(amount, body.payers)\n"
        "    shares = [base + 1 if i < remainder else base for i in range(body.payers)]\n")
    seed = (f"DROP TABLE IF EXISTS {table} CASCADE;\n\nCREATE TABLE {table} (\n    id SERIAL PRIMARY KEY,\n"
            f"    customer TEXT NOT NULL,\n    amount_cents INTEGER NOT NULL\n);\n\n"
            f"INSERT INTO {table} (customer, amount_cents) VALUES\n{sql_values(rows)};\n")
    helpers = f'''

def split(client, {noun}_id, payers):
    return client.post(f"/{table}/{{{noun}_id}}/split", json={{"payers": payers}})
'''
    uneven = [(i + 1, p) for i, a in enumerate(amounts) for p in (3, 7) if a % p][:5]
    public = dedent(f'''\
        from conftest import split


        def test_even_split(client):
            r = split(client, 1, 4)
            assert r.status_code == 200
            assert r.json()["shares"] == {shares(amounts[0], 4)}


        def test_missing_{noun}(client):
            assert split(client, 999, 2).status_code == 404


        def test_zero_payers_rejected(client):
            assert split(client, 1, 0).status_code == 422
        ''')
    regression = dedent(f'''\
        from conftest import seed, split, stored_data


        def test_single_payer_gets_everything(client):
            assert split(client, 2, 1).json()["shares"] == [{amounts[1]}]


        def test_even_three_way(client):
            assert split(client, 1, 3).json() == {{"{noun}_id": 1, "amount_cents": {amounts[0]}, "shares": {shares(amounts[0], 3)}}}


        def test_too_many_payers_rejected(client):
            assert split(client, 1, 21).status_code == 422


        def test_twenty_payers_accepted(client):
            assert split(client, 1, 20).json()["shares"] == {shares(amounts[0], 20)}


        def test_split_changes_no_stored_data(client):
            seed()
            before = stored_data()
            split(client, 2, 3)
            assert stored_data() == before
        ''')
    target = dedent(f'''\
        """Shares must add up to the amount exactly, differ by at most one cent, larger shares first."""

        import pytest

        from conftest import split


        @pytest.mark.parametrize("{noun}_id,payers", {uneven})
        def test_shares_sum_to_total(client, {noun}_id, payers):
            body = split(client, {noun}_id, payers).json()
            assert sum(body["shares"]) == body["amount_cents"]
            assert len(body["shares"]) == payers


        def test_extra_cents_go_to_first_payers(client):
            assert split(client, 2, 3).json()["shares"] == {shares(amounts[1], 3)}
            assert split(client, 3, 7).json()["shares"] == {shares(amounts[2], 7)}
        ''')
    prompt = f'''
You are working on a small FastAPI service that splits a {noun} between several payers.
Amounts are integers in cents.

Bug report from finance: "When a {noun} is split, the shares don't always add up to its amount:
splitting {rows[1][1] / 100:.2f} three ways gives three shares of {amounts[1] // 3 / 100:.2f}."

Fix POST /{table}/{{{noun}_id}}/split so that:
- the shares always add up exactly to the amount
- shares differ from each other by at most 1 cent
- leftover cents go to the first payers
- existing behaviour (validation, 404 for missing {table}, response shape) is unchanged

You may run the tests in tests_public/. Do not modify test files.
'''
    return _files(task_id, "split_rounding", "business-logic", prompt, "target", buggy, fixed, seed, helpers,
                  public, regression, target)


# ---------------------------------------------------------------- tenant scope: lookups by id only (CWE-639)
SKINS_TENANT = [("invoices", "invoice", ["paid", "pending", "overdue", "void"]),
                ("documents", "document", ["draft", "review", "approved", "archived"]),
                ("projects", "project", ["planned", "active", "on_hold", "done"]),
                ("contracts", "contract", ["draft", "signed", "expired", "cancelled"])]


def tenant_scope(rng: random.Random, task_id: str) -> dict[str, str]:
    table, noun, states = rng.choice(SKINS_TENANT)
    rows = []
    for tenant in (1, 2):
        rows += [(tenant, rng.choice(PEOPLE), rng.randint(500, 90000), rng.choice(states[:3]))
                 for _ in range(rng.randint(3, 5))]
    rng.shuffle(rows)
    own = {t: [i + 1 for i, r in enumerate(rows) if r[0] == t] for t in (1, 2)}
    literal = ", ".join(f'"{s}"' for s in states)

    buggy = dedent(f'''\
        from typing import Literal

        from fastapi import Depends, FastAPI, Header, HTTPException
        from pydantic import BaseModel
        from sqlalchemy import text

        from app.db import get_db

        app = FastAPI(title="{table.title()}")


        class StatusUpdate(BaseModel):
            status: Literal[{literal}]


        @app.get("/{table}")
        def list_{table}(x_tenant_id: int = Header(...), db=Depends(get_db)):
            rows = db.execute(
                text("SELECT id, tenant_id, owner, value_cents, status FROM {table} WHERE tenant_id = :tenant ORDER BY id"),
                {{"tenant": x_tenant_id}},
            ).mappings().all()
            return [dict(r) for r in rows]


        @app.get("/{table}/{{{noun}_id}}")
        def get_{noun}({noun}_id: int, x_tenant_id: int = Header(...), db=Depends(get_db)):
            row = db.execute(
                text("SELECT id, tenant_id, owner, value_cents, status FROM {table} WHERE id = :id"),
                {{"id": {noun}_id}},
            ).mappings().first()
            if row is None:
                raise HTTPException(status_code=404, detail="{noun.title()} not found")
            return dict(row)


        @app.patch("/{table}/{{{noun}_id}}/status")
        def update_status({noun}_id: int, body: StatusUpdate, x_tenant_id: int = Header(...), db=Depends(get_db)):
            row = db.execute(
                text("UPDATE {table} SET status = :status WHERE id = :id RETURNING id, tenant_id, owner, value_cents, status"),
                {{"status": body.status, "id": {noun}_id}},
            ).mappings().first()
            db.commit()
            if row is None:
                raise HTTPException(status_code=404, detail="{noun.title()} not found")
            return dict(row)
        ''')
    fixed = buggy.replace(
        f'FROM {table} WHERE id = :id"),\n        {{"id": {noun}_id}},',
        f'FROM {table} WHERE id = :id AND tenant_id = :tenant"),\n        {{"id": {noun}_id, "tenant": x_tenant_id}},').replace(
        f'SET status = :status WHERE id = :id RETURNING',
        f'SET status = :status WHERE id = :id AND tenant_id = :tenant RETURNING').replace(
        f'{{"status": body.status, "id": {noun}_id}},',
        f'{{"status": body.status, "id": {noun}_id, "tenant": x_tenant_id}},')
    seed = (f"DROP TABLE IF EXISTS {table} CASCADE;\n\nCREATE TABLE {table} (\n    id SERIAL PRIMARY KEY,\n"
            f"    tenant_id INTEGER NOT NULL,\n    owner TEXT NOT NULL,\n    value_cents INTEGER NOT NULL,\n"
            f"    status TEXT NOT NULL\n);\n\n"
            f"INSERT INTO {table} (tenant_id, owner, value_cents, status) VALUES\n{sql_values(rows)};\n")
    helpers = f'''

def as_tenant(tenant):
    return {{"X-Tenant-ID": str(tenant)}}


def status_of(row_id):
    with engine.connect() as conn:
        return conn.exec_driver_sql("SELECT status FROM {table} WHERE id = %(id)s", {{"id": row_id}}).scalar_one()
'''
    a, b = own[1][0], own[2][0]
    public = dedent(f'''\
        from conftest import as_tenant, status_of


        def test_list_own_{table}(client):
            assert [r["id"] for r in client.get("/{table}", headers=as_tenant(1)).json()] == {own[1]}


        def test_read_own_{noun}(client):
            r = client.get("/{table}/{a}", headers=as_tenant(1))
            assert r.status_code == 200 and r.json()["tenant_id"] == 1


        def test_update_own_{noun}(client):
            r = client.patch("/{table}/{a}/status", json={{"status": "{states[3]}"}}, headers=as_tenant(1))
            assert r.status_code == 200 and status_of({a}) == "{states[3]}"
        ''')
    regression = dedent(f'''\
        import pytest

        from conftest import as_tenant, status_of


        @pytest.mark.parametrize("tenant,row_id", {[(1, i) for i in own[1][:2]] + [(2, i) for i in own[2][:2]]})
        def test_tenants_read_their_own(client, tenant, row_id):
            assert client.get(f"/{table}/{{row_id}}", headers=as_tenant(tenant)).json()["tenant_id"] == tenant


        def test_missing_{noun}_is_404(client):
            assert client.get("/{table}/999", headers=as_tenant(1)).status_code == 404


        def test_invalid_status_rejected(client):
            assert client.patch("/{table}/{b}/status", json={{"status": "bogus"}}, headers=as_tenant(2)).status_code == 422


        def test_other_tenant_list(client):
            assert [r["id"] for r in client.get("/{table}", headers=as_tenant(2)).json()] == {own[2]}
        ''')
    target = dedent(f'''\
        """A tenant can neither read nor change another tenant's {table} (CWE-639)."""

        import pytest

        from conftest import as_tenant, status_of


        @pytest.mark.parametrize("tenant,row_id", {[(1, i) for i in own[2][:2]] + [(2, i) for i in own[1][:2]]})
        def test_other_tenants_{noun}_is_404(client, tenant, row_id):
            assert client.get(f"/{table}/{{row_id}}", headers=as_tenant(tenant)).status_code == 404


        @pytest.mark.parametrize("tenant,row_id", [(1, {b}), (2, {a})])
        def test_cannot_change_other_tenants_{noun}(client, tenant, row_id):
            before = status_of(row_id)
            r = client.patch(f"/{table}/{{row_id}}/status", json={{"status": "{states[3]}"}}, headers=as_tenant(tenant))
            assert r.status_code == 404 and status_of(row_id) == before
        ''')
    prompt = f'''
You are working on a small multi-tenant FastAPI service for {table}, backed by PostgreSQL. The API
gateway authenticates each caller and forwards their tenant in the X-Tenant-ID header.

Security review finding (high): GET /{table}/{{{noun}_id}} and PATCH /{table}/{{{noun}_id}}/status look
{table} up by id only. Any tenant can read or change another tenant's {table} by guessing ids.

Fix both endpoints so that:
- a tenant can only read or update {table} whose tenant_id matches X-Tenant-ID
- another tenant's {noun} returns 404, exactly like a missing one (do not reveal it exists)
- a rejected update must not change the database
- existing behaviour for a tenant's own {table} is unchanged

You may run the tests in tests_public/. Do not modify test files.
'''
    return _files(task_id, "tenant_scope", "broken-access-control", prompt, "security", buggy, fixed, seed,
                  helpers, public, regression, target, cwe="CWE-639", per_test_seed=True)


FAMILIES = {"pagination": pagination, "split_rounding": split_rounding, "tenant_scope": tenant_scope}
