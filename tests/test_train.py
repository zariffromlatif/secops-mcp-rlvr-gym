"""Training reward: answer parsing, one scoring run giving every verifier, sample logging, run report.
The scoring tests need the Postgres from runtime/docker-compose.yml."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import score_patch as sp
from train import evaluate, report
from train.dataset import prompt
from train.grpo import Reward, completion_text, gold_main
from train.scoring import Scorer, extract_main

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def patched_main(task: str, patch: str) -> str:
    sp.TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
        sp.prepare_workdir(TASKS / task, Path(tmp))
        assert sp.apply_patch(Path(tmp), TASKS / task / patch)[0]
        return (Path(tmp) / "app" / "main.py").read_text()


@pytest.fixture(scope="module")
def scorer():
    return Scorer("local", workers=2)


def test_the_last_code_block_is_the_answer():
    assert extract_main("plan\n```python\na = 1\n```\nthen\n```py\nb = 2\n```") == "b = 2\n"
    assert extract_main("```\nc = 3\n```") == "c = 3\n"
    assert extract_main("no code here") is None and extract_main(None) is None
    assert completion_text([{"role": "assistant", "content": "x"}]) == "x" and completion_text("y") == "y"


def test_prompt_shows_code_and_public_tests_but_not_hidden_tests():
    text = prompt(TASKS / "revenue_double_count_007")[1]["content"]
    assert '<file path="app/main.py">' in text and '<file path="tests_public/' in text
    assert "hidden/" not in text and "gold" not in text


def test_gold_solves_and_buggy_code_passes_only_the_public_tests(scorer):
    task = TASKS / "revenue_double_count_007"
    gold = scorer.score(task, gold_main(task))
    assert gold["v1"] == gold["v2"] == gold["v3"] == 1.0 and gold["solved"]
    buggy = scorer.score(task, (task / "app" / "main.py").read_text())
    assert buggy["v1"] == 1.0 and buggy["v2"] < 1.0 and buggy["v3"] < 1.0 and not buggy["solved"]


def test_static_gate_separates_v2_from_v3(scorer):
    # Every test passes, but the SQL is still built with an f-string.
    r = scorer.score(TASKS / "invoice_sort_001", patched_main("invoice_sort_001", "exploits/fstring_via_variable.patch"))
    assert r["v1"] == r["v2"] == 1.0 and r["v3"] < 1.0 and not r["solved"]


def test_unparseable_answers_score_zero_without_running_tests(scorer):
    for answer in (None, "def broken(:\n"):
        r = scorer.score(TASKS / "revenue_double_count_007", answer)
        assert (r["v1"], r["v2"], r["v3"], r["solved"]) == (0.0, 0.0, 0.0, False)


def test_reward_returns_the_chosen_verifier_and_logs_all(scorer, tmp_path):
    task = TASKS / "revenue_double_count_007"
    reward = Reward("v1", scorer, tmp_path, workers=2)
    metrics = {}
    answers = [[{"role": "assistant", "content": f"```python\n{code}```"}]
               for code in (gold_main(task), (task / "app" / "main.py").read_text())] + ["no code"]
    out = reward([None] * 3, answers, [str(task)] * 3, trainer_state=SimpleNamespace(global_step=7),
                 log_metric=metrics.__setitem__)
    assert out == [1.0, 1.0, 0.0]
    rows = [json.loads(line) for line in (tmp_path / "samples.jsonl").read_text().splitlines()]
    assert [(r["step"], r["reward"], r["solved"]) for r in rows] == [(7, "v1", True), (7, "v1", False), (7, "v1", False)]
    assert metrics["verifier/v1"] == pytest.approx(2 / 3) and metrics["verifier/solved"] == pytest.approx(1 / 3)


def test_report_counts_gamed_samples():
    samples = [{"step": s, "task": "t", "reward": "v2", "v1": v1, "v2": v2, "v3": 0.5, "solved": solved}
               for s, v1, v2, solved in [(0, 1.0, 1.0, True), (0, 1.0, 0.5, False), (0, 0.5, 0.5, False),
                                         (12, 1.0, 1.0, False)]]
    first, second = report.buckets(samples, 10)
    assert first["n"] == 3 and first["solved"] == pytest.approx(1 / 3)
    assert first["gamed_v1"] == pytest.approx(1 / 3) and first["gamed_v2"] == 0
    assert second["steps"] == "10-19" and second["gamed_v1"] == second["gamed_v2"] == 1.0
    assert "| t | 1 | 0.500 | 0.0% | 100.0% | 100.0% |" in report.render({"run": samples}, 10, last=5)


def test_deadline_is_the_next_time_the_clock_shows_it():
    import time

    from train.grpo import parse_deadline

    at = parse_deadline("12:40")
    assert time.time() < at <= time.time() + 24 * 3600 and time.localtime(at)[3:5] == (12, 40)
    assert parse_deadline(None) is None


def test_evaluation_summary_marks_tasks_without_learning_signal():
    rows = [{"task": "a", "v1": 1.0, "v2": 0.5, "v3": v3, "solved": v3 == 1.0} for v3 in (0.5, 1.0)]
    rows += [{"task": "b", "v1": 1.0, "v2": 0.5, "v3": 0.5, "solved": False} for _ in range(2)]
    s = evaluate.summarize(rows)
    assert s["tasks"]["a"] == {"samples": 2, "v1": 1.0, "v2": 0.5, "v3": 0.75, "solved": 0.5, "any": True, "signal": True}
    assert s["tasks"]["b"]["signal"] is False and s["tasks"]["b"]["any"] is False
    assert s["overall"]["signal"] == 0.5 and s["overall"]["solved"] == 0.25


def test_rescore_flags_answers_recorded_higher_than_they_score(scorer, tmp_path):
    from train import rescore

    task = TASKS / "revenue_double_count_007"
    gold, buggy = gold_main(task), (task / "app" / "main.py").read_text()
    honest = scorer.score(task, buggy)
    row = lambda code, s, step: {"step": step, "task": task.name, "answer": f"```python\n{code}```",  # noqa: E731
                                 **{k: s[k] for k in ("v1", "v2", "v3", "solved")}}
    samples = tmp_path / "run" / "samples.jsonl"
    samples.parent.mkdir()
    rows = [row(gold, {"v1": 1.0, "v2": 1.0, "v3": 1.0, "solved": True}, 1),
            row(buggy, honest, 1),
            row(buggy, {"v1": 1.0, "v2": 1.0, "v3": 1.0, "solved": True}, 2),  # what a scorer trick would record
            {**row(gold, {"v1": 1.0, "v2": 1.0, "v3": 1.0, "solved": True}, 3), "task": "not_a_task_999"}]
    samples.write_text("".join(json.dumps(r) + "\n" for r in rows))

    loaded = rescore.load([tmp_path])
    assert len(loaded) == 4 and [rescore.passing(r) for r in loaded] == [True, False, True, True]
    cache = tmp_path / "cache.jsonl"
    isolated = rescore.rescore(loaded, scorer, [TASKS], workers=2, cache=cache)
    assert len(isolated) == 2 and len(cache.read_text().splitlines()) == 2  # two distinct answers, one task missing
    assert [rescore.compare(r, isolated[rescore.key(r)]) for r in loaded[:3]] == ["same", "same", "inflated"]
    text, inflated = rescore.render(loaded, isolated, "local")
    assert inflated == 1 and "| 4 | 2 | 1 | 0 | 1 |" in text and "not_a_task_999" in text
    # A second run scores nothing again.
    assert rescore.rescore(loaded, None, [TASKS], workers=2, cache=cache) == isolated


def test_campaign_treats_docker_not_installed_as_not_running(monkeypatch):
    from train import campaign

    monkeypatch.setattr(campaign.shutil, "which", lambda name: None)  # no docker executable at all
    assert campaign.docker_runs() is False
