"""Contamination probes, with a fake model: one that has memorized the repository and one that has not."""

from pathlib import Path

from audit import contamination as c

ROOT = Path(__file__).resolve().parents[1]


class Memorized:
    """Answers with the true canary GUID and the true rest of any repository test file."""
    model = "memorized"

    def chat(self, messages, **_):
        text = messages[-1]["content"]
        if "Complete this line" in text:
            return {"content": f"{c.PREFIX} {c.GUID}"}
        name = text.split("tests/", 1)[1].split(" ", 1)[0]
        path = ROOT / "tasks" / name.split("/")[0] / "hidden" / name.split("/")[1]
        return {"content": path.read_text() if path.exists() else ""}


class Fresh:
    model = "fresh"

    def chat(self, messages, **_):
        return {"content": "def test_something():\n    assert True\n"}


def test_a_memorizing_model_is_flagged_and_a_fresh_one_is_not():
    seen = c.run(Memorized(), samples=2)
    assert seen["canary"] == {"samples": 2, "completed": 2}
    assert seen["recall"] == 1.0 and seen["control_recall"] == 0.0
    fresh = c.run(Fresh(), samples=2)
    assert fresh["canary"]["completed"] == 0 and fresh["recall"] == 0.0
    assert len(fresh["tasks"]) >= 17 and all(r["lines"] > 0 for r in fresh["tasks"] + fresh["control"])
