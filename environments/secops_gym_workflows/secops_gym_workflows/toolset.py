"""Per-rollout MCP tool server: mock payments, ledger, tickets and chat.

The episode database is created on the first tool call and its name is pushed to
the rollout state, where the task's scorer finds it. Tool calls run as the
unprivileged `wf_agent` role (read-only SQL, 5 s statement timeout). Each workflow
offers only the tools its task.yaml lists, and refuses calls past its max_steps.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

import verifiers.v1 as vf
from secops_gym_workflows._vendor import mcp_tools
from secops_gym_workflows._vendor import workflows as episodes

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # older mcp
    ToolError = RuntimeError

WORKFLOWS = Path(__file__).resolve().parent / "data" / "workflows"


class WorkflowState(vf.State):
    db_name: str | None = None
    score: float = 0.0


class CompanyToolset(vf.Toolset[vf.ToolsetConfig, WorkflowState]):
    TOOL_PREFIX = None  # advertise bare names: sql_query, issue_refund, ...

    def __init__(self, config: vf.ToolsetConfig) -> None:
        super().__init__(config)
        self.workflow_id: str | None = None
        self.tools: list[str] = list(mcp_tools.TOOLS)
        self.max_steps: int | None = None
        self._steps = 0
        self._db_name: str | None = None
        self._engines: dict = {}

    async def setup_task(self, task) -> None:
        data = getattr(task, "data", task)
        self.workflow_id = data.workflow_id
        self.tools, self.max_steps = episodes.limits(WORKFLOWS / self.workflow_id)

    def register(self, mcp) -> None:
        super().register(mcp)
        for name in set(mcp_tools.TOOLS) - set(self.tools):  # advertise only this workflow's tools
            mcp.remove_tool(name)

    def _call(self, name: str, **args):
        self._steps += 1
        if self.max_steps is not None and self._steps > self.max_steps:
            raise ToolError(f"step limit reached: this task allows {self.max_steps} tool calls")
        # The rollout state carries db_name to the scorer; the instance copy keeps one database
        # per rollout even when no state channel is attached (direct use, tests).
        db_name = self.state.db_name or self._db_name
        if db_name is None:
            db_name = episodes.create_episode_db(WORKFLOWS / self.workflow_id)
        self._db_name = self.state.db_name = db_name
        engine = self._engines.get(db_name)
        if engine is None:
            engine = self._engines[db_name] = create_engine(episodes.agent_url(db_name))
        try:
            with engine.begin() as conn:
                return mcp_tools.call_tool(conn, name, args, self.tools)
        except mcp_tools.ToolError as exc:
            raise ToolError(str(exc)) from None
        except DBAPIError:
            # Don't leak connection details (hosts, ports) to the agent.
            raise ToolError("internal error: the company database is temporarily unavailable") from None

    @vf.tool
    def sql_query(self, query: str) -> list[dict]:
        """Run a read-only SQL query (SELECT or WITH) and return up to 200 rows.

        Tables: customers(id, name, email, phone), payments(id, customer_id, amount_cents, status,
        webhook_id, created_at), ledger_credits(id, customer_id, payment_id, amount_cents, reason),
        tickets(id, customer_id, title, body, status, linked_payment_id, resolution),
        messages(id, channel, text).
        Values are lowercase: payments.status is 'succeeded', 'failed' or 'refunded';
        tickets.status is 'open' or 'closed'. Timestamps are UTC.
        """
        return self._call("sql_query", query=query)

    @vf.tool
    def issue_refund(self, payment_id: int, reason: str) -> dict:
        """Refund a succeeded payment in full and record a ledger credit for it."""
        return self._call("issue_refund", payment_id=payment_id, reason=reason)

    @vf.tool
    def create_ticket(self, customer_id: int, title: str, body: str, linked_payment_id: int | None = None) -> dict:
        """Open a support ticket for a customer, optionally linked to a payment."""
        return self._call(
            "create_ticket", customer_id=customer_id, title=title, body=body, linked_payment_id=linked_payment_id
        )

    @vf.tool
    def close_ticket(self, ticket_id: int, resolution: str) -> dict:
        """Close an open support ticket with a short resolution note."""
        return self._call("close_ticket", ticket_id=ticket_id, resolution=resolution)

    @vf.tool
    def post_message(self, channel: str, text: str) -> dict:
        """Post a message to a team chat channel such as #billing or #support."""
        return self._call("post_message", channel=channel, text=text)


if __name__ == "__main__":
    CompanyToolset.run()
