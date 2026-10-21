"""Mock company tools for workflow tasks: payments, ledger, support tickets, team chat.

Every tool takes an open SQLAlchemy connection as its first argument and returns
JSON-serialisable data. Errors are raised as ToolError so the caller can report
them back to the agent without changing any state.
"""

from __future__ import annotations

import datetime as dt
import decimal

from sqlalchemy import text


class ToolError(Exception):
    pass


def _jsonable(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def sql_query(conn, query: str) -> list[dict]:
    """Run a read-only SQL query (SELECT or WITH) and return up to 200 rows.

    Tables: customers, payments, ledger_credits, tickets, messages. Status values are lowercase
    (payments: 'succeeded' / 'failed' / 'refunded'; tickets: 'open' / 'closed'). Timestamps are UTC.
    """
    head = query.strip().split(None, 1)[0].lower() if query.strip() else ""
    if head not in {"select", "with"} or ";" in query.strip().rstrip(";"):
        raise ToolError("only a single SELECT or WITH query is allowed")
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
    # Raw cursor with no parameters, so '%' in LIKE patterns is passed through literally.
    cursor = conn.connection.cursor()
    try:
        cursor.execute(query)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(200)
    except Exception as exc:  # surface SQL errors to the agent as tool errors
        raise ToolError(f"query failed: {str(exc).splitlines()[0]}") from None
    finally:
        cursor.close()
    return [{c: _jsonable(v) for c, v in zip(columns, row)} for row in rows]


def issue_refund(conn, payment_id: int, reason: str) -> dict:
    """Refund a succeeded payment in full and record a ledger credit for it."""
    payment = conn.execute(
        text("SELECT id, customer_id, amount_cents, status FROM payments WHERE id = :id FOR UPDATE"),
        {"id": payment_id},
    ).mappings().first()
    if payment is None:
        raise ToolError(f"payment {payment_id} not found")
    if payment["status"] != "succeeded":
        raise ToolError(f"payment {payment_id} is not refundable (status={payment['status']})")
    conn.execute(text("UPDATE payments SET status = 'refunded' WHERE id = :id"), {"id": payment_id})
    credit_id = conn.execute(
        text(
            "INSERT INTO ledger_credits (customer_id, payment_id, amount_cents, reason) "
            "VALUES (:customer, :payment, :amount, :reason) RETURNING id"
        ),
        {"customer": payment["customer_id"], "payment": payment_id, "amount": payment["amount_cents"], "reason": reason},
    ).scalar_one()
    return {"payment_id": payment_id, "refunded_cents": payment["amount_cents"], "ledger_credit_id": credit_id}


def create_ticket(conn, customer_id: int, title: str, body: str, linked_payment_id: int | None = None) -> dict:
    """Open a support ticket for a customer, optionally linked to a payment."""
    if conn.execute(text("SELECT 1 FROM customers WHERE id = :id"), {"id": customer_id}).first() is None:
        raise ToolError(f"customer {customer_id} not found")
    if linked_payment_id is not None and conn.execute(
        text("SELECT 1 FROM payments WHERE id = :id"), {"id": linked_payment_id}
    ).first() is None:
        raise ToolError(f"payment {linked_payment_id} not found")
    ticket_id = conn.execute(
        text(
            "INSERT INTO tickets (customer_id, title, body, status, linked_payment_id) "
            "VALUES (:customer, :title, :body, 'open', :payment) RETURNING id"
        ),
        {"customer": customer_id, "title": title, "body": body, "payment": linked_payment_id},
    ).scalar_one()
    return {"ticket_id": ticket_id, "status": "open"}


def close_ticket(conn, ticket_id: int, resolution: str) -> dict:
    """Close an open support ticket with a short resolution note."""
    status = conn.execute(
        text("SELECT status FROM tickets WHERE id = :id FOR UPDATE"), {"id": ticket_id}
    ).scalar()
    if status is None:
        raise ToolError(f"ticket {ticket_id} not found")
    if status != "open":
        raise ToolError(f"ticket {ticket_id} is already {status}")
    conn.execute(
        text("UPDATE tickets SET status = 'closed', resolution = :resolution WHERE id = :id"),
        {"id": ticket_id, "resolution": resolution},
    )
    return {"ticket_id": ticket_id, "status": "closed"}


def post_message(conn, channel: str, text_: str) -> dict:
    """Post a message to a team chat channel such as #billing or #support."""
    if not channel.startswith("#"):
        raise ToolError("channel must start with '#'")
    message_id = conn.execute(
        text("INSERT INTO messages (channel, text) VALUES (:channel, :text) RETURNING id"),
        {"channel": channel, "text": text_},
    ).scalar_one()
    return {"message_id": message_id}


TOOLS = {
    "sql_query": sql_query,
    "issue_refund": issue_refund,
    "create_ticket": create_ticket,
    "close_ticket": close_ticket,
    "post_message": post_message,
}

# Argument names as agents see them (`text` would shadow sqlalchemy.text inside the module).
ARG_ALIASES = {"post_message": {"text": "text_"}}

BASE_SCHEMA = """
DROP TABLE IF EXISTS messages, tickets, ledger_credits, payments, customers CASCADE;

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refunded')),
    webhook_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE ledger_credits (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    amount_cents INTEGER NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE tickets (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    linked_payment_id INTEGER REFERENCES payments(id),
    resolution TEXT
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    text TEXT NOT NULL
);
"""


def call_tool(conn, name: str, args: dict):
    """Dispatch one tool call. Raises ToolError for unknown tools or bad arguments."""
    if name not in TOOLS:
        raise ToolError(f"unknown tool: {name}")
    aliases = ARG_ALIASES.get(name, {})
    kwargs = {aliases.get(k, k): v for k, v in (args or {}).items()}
    try:
        return TOOLS[name](conn, **kwargs)
    except TypeError as exc:
        raise ToolError(f"bad arguments for {name}: {exc}") from None
