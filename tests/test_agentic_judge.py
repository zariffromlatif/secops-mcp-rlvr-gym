"""V5 runs what it judges: tool plumbing against a live sandbox app and a replayed workflow.

Needs Docker (patch tasks) and Postgres (workflows).
"""

import json
from pathlib import Path

from audit import agentic_judge as aj
from audit.rescore import original_app_files

ROOT = Path(__file__).resolve().parents[1]


class ScriptedJudge:
    """Plays back tool calls, one per turn, and records what each tool returned."""

    model = "scripted"

    def __init__(self, calls):
        self.calls, self.results, self.turns = list(calls), [], 0

    def chat(self, messages, tools=None, **options):
        self.turns += 1
        self.results += [json.loads(m["content"]) for m in messages if m["role"] == "tool"][len(self.results):]
        name, args = self.calls.pop(0)
        return {"content": "", "tool_calls": [
            {"id": f"c{self.turns}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def test_patch_judge_calls_the_running_app_and_reads_its_database():
    task = "revenue_double_count_007"
    judge = ScriptedJudge([
        ("http_request", {"method": "get", "path": "reports/revenue", "query": {}, "json_body": {}, "headers": {}}),
        ("sql_query", {"query": "SELECT COUNT(*) AS n FROM payments"}),
        ("sql_query", {"query": "DELETE FROM payments"}),
        ("reset_data", {}),
        ("submit_verdict", {"verdict": "fail", "reason": "Acme's multi-payment invoice is still counted twice"}),
    ])
    with aj.live_app(task, original_app_files(task)) as live:
        answer = aj.run_judge(judge, aj.patch_prompt(task, original_app_files(task)), aj.PATCH_TOOLS, live)

    http, count, write, reset = judge.results
    acme = next(r for r in json.loads(http["body"]) if r["customer"] == "Acme Ltd")
    assert http["status"] == 200 and acme["revenue_cents"] == 20000  # the bug, observed live
    assert count == [{"n": "8"}]
    assert "only a single SELECT" in write["error"]
    assert reset == "seed data reloaded"
    assert answer == {"verdict": False, "reason": "Acme's multi-payment invoice is still counted twice", "steps": 5}


def test_workflow_judge_queries_the_final_state_and_caches(tmp_path):
    wf = "duplicate_webhook_refunds_101"
    solution = {"kind": "workflow", "task": wf, "calls": json.loads((ROOT / "workflows" / wf / "gold.json").read_text())}
    client = ScriptedJudge([
        ("sql_query", {"query": "SELECT status FROM payments WHERE id = 2"}),
        ("submit_verdict", {"verdict": "pass", "reason": "duplicates refunded"}),
    ])
    judge = aj.AgenticJudge(client, cache=tmp_path / "v5.jsonl")
    assert judge.judge(solution)["verdict"] is True
    assert client.results == [[{"status": "refunded"}]]
    assert aj.AgenticJudge(client, cache=tmp_path / "v5.jsonl").judge(solution)["verdict"] is True
    assert client.turns == 2  # the second judge read the cache


def test_no_verdict_within_the_step_limit():
    class Silent:
        def chat(self, messages, **options):
            return {"content": "Looks fine to me."}

    answer = aj.run_judge(Silent(), "prompt", aj.WORKFLOW_TOOLS, impl=None, max_steps=3)
    assert answer["verdict"] is None and answer["steps"] == 3
