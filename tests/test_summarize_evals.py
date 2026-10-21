"""The results summarizer counts provider errors separately from failed attempts."""

import csv
import json

import summarize_evals


def episode(task, reward=None, solved=None, error=None, **gates):
    metrics = {**gates} if solved is None else {**gates, "solved": solved}
    return {
        "task": {"data": {"name": task}},
        "ok": error is None,
        "num_total_tokens": 100,
        "traces": [{
            "ok": error is None,
            "rewards": {} if reward is None else {"reward": {"score": reward, "weight": 1.0}},
            "metrics": metrics,
            "errors": [] if error is None else [{"message": error}],
        }],
    }


def test_summary_excludes_errored_attempts(tmp_path, monkeypatch):
    run = tmp_path / "secops_gym_patches--qwen--qwen3.8-27b--bash--abc123"
    run.mkdir()
    rows = [
        episode("task_a", 1.0, 1.0, gate_regression=0.8, gate_target=1.5),
        episode("task_a", 0.5, 0.0, gate_regression=0.8, gate_target=0.0),
        episode("task_a", error="upstream 429: rate limit"),
        episode("task_b", error="upstream 413: request too large"),
    ]
    (run / "traces.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(summarize_evals, "OUT", tmp_path / "out")

    summarize_evals.summarize(run)

    with open(tmp_path / "out" / "secops_gym_patches__qwen_qwen3.8-27b__abc123.csv") as f:
        table = {r["task"]: r for r in csv.DictReader(f)}
    assert table["task_a"]["attempts"] == "3" and table["task_a"]["errored"] == "1"
    assert table["task_a"]["solve_rate"] == "0.5" and table["task_a"]["mean_reward"] == "0.75"
    assert table["task_b"]["solve_rate"] == ""  # only an errored attempt: no rate, not 0
    assert table["ALL"]["solved"] == "1"
