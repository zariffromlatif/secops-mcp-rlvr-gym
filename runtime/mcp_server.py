"""MCP server exposing the mock company tools for one workflow episode.

Start an episode, point the server at its database, connect any MCP client:

    uv sync --extra mcp
    uv run python runtime/workflows.py start workflows/duplicate_webhook_refunds_101
    WORKFLOW_DB_URL=<printed url> uv run python runtime/mcp_server.py workflows/duplicate_webhook_refunds_101
    uv run python runtime/workflows.py finish workflows/duplicate_webhook_refunds_101 <db_name>

The server speaks stdio. Given a workflow folder, it offers only the tools that workflow's
task.yaml lists and refuses calls past its max_steps; without one, it offers every tool.
Every call runs in its own transaction as the unprivileged `wf_agent` role.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mcp_tools  # noqa: E402

engine = create_engine(os.environ.get("WORKFLOW_DB_URL", "postgresql+psycopg://wf_agent:wf_agent@localhost:5433/postgres"))
server = MCPServer("secops-gym-workflows", instructions="Mock payments, ledger, ticketing and chat tools.")
max_steps: int | None = None
steps = 0


def _run(name: str, **args):
    global steps
    steps += 1
    if max_steps is not None and steps > max_steps:
        raise ToolError(f"step limit reached: this task allows {max_steps} tool calls")
    try:
        with engine.begin() as conn:
            return mcp_tools.call_tool(conn, name, args)
    except mcp_tools.ToolError as exc:
        raise ToolError(str(exc)) from None  # shown to the agent as an is_error result
    except DBAPIError:
        # Don't leak connection details (hosts, ports) to the agent.
        raise ToolError("internal error: the company database is temporarily unavailable") from None


@server.tool()
def sql_query(query: str) -> list[dict]:
    """Run a read-only SQL query (SELECT or WITH) and return up to 200 rows.

    Tables: customers(id, name, email, phone), payments(id, customer_id, amount_cents, status,
    webhook_id, created_at), ledger_credits(id, customer_id, payment_id, amount_cents, reason),
    tickets(id, customer_id, title, body, status, linked_payment_id, resolution),
    messages(id, channel, text).
    Values are lowercase: payments.status is 'succeeded', 'failed' or 'refunded';
    tickets.status is 'open' or 'closed'. Timestamps are UTC.
    """
    return _run("sql_query", query=query)


@server.tool()
def issue_refund(payment_id: int, reason: str) -> dict:
    """Refund a succeeded payment in full and record a ledger credit for it."""
    return _run("issue_refund", payment_id=payment_id, reason=reason)


@server.tool()
def create_ticket(customer_id: int, title: str, body: str, linked_payment_id: int | None = None) -> dict:
    """Open a support ticket for a customer, optionally linked to a payment."""
    return _run("create_ticket", customer_id=customer_id, title=title, body=body, linked_payment_id=linked_payment_id)


@server.tool()
def close_ticket(ticket_id: int, resolution: str) -> dict:
    """Close an open support ticket with a short resolution note."""
    return _run("close_ticket", ticket_id=ticket_id, resolution=resolution)


@server.tool()
def post_message(channel: str, text: str) -> dict:
    """Post a message to a team chat channel such as #billing or #support."""
    return _run("post_message", channel=channel, text=text)


def restrict(wf_dir: Path) -> None:
    """Offer only the tools the workflow's task.yaml lists, and at most its max_steps calls."""
    global max_steps
    from workflows import limits

    offered, max_steps = limits(wf_dir)
    for tool in set(mcp_tools.TOOLS) - set(offered):
        server.remove_tool(tool)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        restrict(Path(sys.argv[1]))
    server.run("stdio")
