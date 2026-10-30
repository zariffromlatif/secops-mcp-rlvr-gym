"""Safety limits and business rules of the mock company tools. Needs Postgres (DATABASE_URL)."""

import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import workflows as episodes

WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "duplicate_webhook_refunds_101"


@pytest.fixture
def db():
    name = episodes.create_episode_db(WORKFLOW)
    yield name
    episodes.drop_episode_db(name)


def call(db, tool, **args):
    results, errors = episodes.replay(db, [{"tool": tool, "args": args}], max_steps=1)
    return results[0]


def admin_scalar(db, sql):
    engine = create_engine(make_url(episodes.ADMIN_URL).set(database=db))
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql)).scalar_one()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE payments SET status = 'refunded'",
        "SELECT 1; DELETE FROM payments",
        "WITH gone AS (DELETE FROM payments RETURNING id) SELECT * FROM gone",
        "DELETE FROM payments",
    ],
)
def test_sql_query_cannot_write(db, query):
    assert not call(db, "sql_query", query=query)["ok"]
    assert admin_scalar(db, "SELECT COUNT(*) FROM payments WHERE status = 'refunded'") == 0
    assert admin_scalar(db, "SELECT COUNT(*) FROM payments") == 10


def test_sql_query_has_statement_timeout(db):
    started = time.monotonic()
    result = call(db, "sql_query", query="SELECT pg_sleep(30)")
    assert not result["ok"] and "timeout" in result["error"]
    assert time.monotonic() - started < 15


def test_sql_query_cannot_use_superuser_functions(db):
    result = call(db, "sql_query", query="SELECT pg_read_file('/etc/hostname')")
    assert not result["ok"] and "permission denied" in result["error"]


def test_sql_query_passes_like_patterns_through(db):
    result = call(db, "sql_query", query="SELECT COUNT(*) AS n FROM payments WHERE webhook_id LIKE 'wh_1003%'")
    assert result["ok"] and result["result"] == [{"n": 3}]


def test_refund_creates_ledger_credit_once(db):
    first = call(db, "issue_refund", payment_id=2, reason="duplicate")
    assert first["ok"] and first["result"]["refunded_cents"] == 2500
    assert not call(db, "issue_refund", payment_id=2, reason="again")["ok"]
    assert admin_scalar(db, "SELECT COUNT(*) FROM ledger_credits WHERE payment_id = 2") == 1


def test_failed_payment_is_not_refundable(db):
    result = call(db, "issue_refund", payment_id=9, reason="x")
    assert not result["ok"] and "not refundable" in result["error"]


def test_ticket_closes_only_once(db):
    ticket = call(db, "create_ticket", customer_id=1, title="t", body="b")["result"]["ticket_id"]
    assert call(db, "close_ticket", ticket_id=ticket, resolution="done")["ok"]
    assert not call(db, "close_ticket", ticket_id=ticket, resolution="again")["ok"]


def test_channel_must_start_with_hash(db):
    assert not call(db, "post_message", channel="billing", text="hi")["ok"]
    assert call(db, "post_message", channel="#billing", text="hi")["ok"]


def test_unknown_tool_and_bad_arguments_are_errors(db):
    assert "unknown tool" in call(db, "drop_tables")["error"]
    assert "bad arguments" in call(db, "issue_refund", payment=2)["error"]


def test_mcp_server_offers_only_the_workflows_tools():
    import asyncio

    pytest.importorskip("mcp")
    import mcp_server

    mcp_server.restrict(Path(__file__).resolve().parents[1] / "workflows" / "q1_vip_escalation_104")
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names == {"sql_query", "close_ticket", "post_message"}
    mcp_server.steps = mcp_server.max_steps
    with pytest.raises(Exception, match="step limit"):
        mcp_server._run("sql_query", query="SELECT 1")
