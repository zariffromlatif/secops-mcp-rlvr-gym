"""The red-team loop scores each candidate and keeps the solved ones. Needs Postgres (DATABASE_URL)."""

import json
from pathlib import Path

from audit import corpus, hacker
from audit.llm import json_object

TASK = Path(__file__).resolve().parents[1] / "tasks" / "daily_report_timezone_006"


class ScriptedAttacker:
    model = "scripted"

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, **options):
        self.seen.append(messages[-1]["content"])
        return {"content": self.replies.pop(0)}


def reply(files: dict, how: str) -> str:
    return "Here is my attempt:\n```json\n" + json.dumps({"files": files, "how": how}) + "\n```"


def test_loop_scores_candidates_and_keeps_solved_ones(tmp_path):
    special_cased, _ = corpus._patched_app(TASK, TASK / "exploits" / "hardcoded_dhaka_offset.patch")
    gold, _ = corpus._patched_app(TASK, TASK / "gold.patch")
    attacker = ScriptedAttacker([
        "I can't produce JSON today.",
        reply({"app/main.py": special_cased["app/main.py"]}, "only Asia/Dhaka gets an offset"),
        reply({"app/main.py": gold["app/main.py"], "../../etc/passwd": "x"}, "a correct fix, as it turns out"),
    ])
    summary = hacker.attack(TASK, attacker, attempts=3, sandbox="local", out=tmp_path)

    first, second, third = summary["attempts"]
    assert "error" in first
    assert not second["solved"] and second["target"] < 1.5
    assert third["solved"]
    assert summary["suspected_exploits"] == ["attempt-3.patch"]
    assert "Attempt 2: not solved" in attacker.seen[2]  # the attacker sees its earlier result
    assert "etc/passwd" not in (tmp_path / "attempt-3.patch").read_text()  # paths outside the task are ignored
    assert json.loads((tmp_path / "summary.json").read_text())["task"] == TASK.name


def test_json_object_takes_the_last_top_level_object():
    assert json_object('first {"a": 1} then {"b": {"c": 2}} done') == {"b": {"c": 2}}
    assert json_object("no json here") is None
