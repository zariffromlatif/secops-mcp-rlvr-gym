"""The Prime toolset offers each workflow only its own tools, up to its step limit. Needs Postgres."""

import asyncio
import types

import pytest

toolset = pytest.importorskip("secops_gym_workflows.toolset", reason="needs --extra envs and scripts/sync_envs.py")


def setup(workflow_id: str):
    ts = toolset.CompanyToolset(toolset.vf.ToolsetConfig())
    asyncio.run(ts.setup_task(types.SimpleNamespace(workflow_id=workflow_id)))
    return ts


def test_only_the_workflows_tools_are_advertised():
    from mcp.server import MCPServer

    mcp = MCPServer("test")
    setup("q1_vip_escalation_104").register(mcp)
    assert {t.name for t in asyncio.run(mcp.list_tools())} == {"sql_query", "close_ticket", "post_message"}


def test_unoffered_tools_and_calls_past_max_steps_are_refused():
    ts = setup("q1_vip_escalation_104")
    with pytest.raises(toolset.ToolError, match="not available"):
        ts._call("issue_refund", payment_id=1, reason="goodwill")
    ts.max_steps = ts._steps + 1
    try:
        assert ts._call("sql_query", query="SELECT 1 AS one") == [{"one": 1}]
        with pytest.raises(toolset.ToolError, match="step limit"):
            ts._call("sql_query", query="SELECT 1 AS one")
    finally:
        if ts._db_name:
            toolset.episodes.drop_episode_db(ts._db_name)
