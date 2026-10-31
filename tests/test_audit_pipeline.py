"""Audit pipeline pieces that need no database: collection, judging, blind export, statistics."""

import csv
import json

import pytest

from audit import analyze, judge as judge_mod, labels
from audit.collect import collect


# ---------------------------------------------------------------- statistics
def test_kappa_known_values():
    assert analyze.cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    # 3/4 observed agreement, 0.5 expected by chance -> 0.5
    assert analyze.cohens_kappa([True, True, False, False], [True, False, False, False]) == pytest.approx(0.5)


def test_rates_define_false_positive_as_wrong_solution_rewarded():
    pairs = [(True, False), (False, False), (True, True), (False, True)]  # (verifier_pass, label_pass)
    r = analyze.rates(pairs)
    assert r["fpr"] == 0.5 and r["fnr"] == 0.5 and r["acc"] == 0.5


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    pairs = [(True, False)] * 3 + [(False, False)] * 7 + [(True, True)] * 10
    low, high = analyze.bootstrap(pairs, "fpr")
    assert (low, high) == analyze.bootstrap(pairs, "fpr")
    assert low <= 0.3 <= high


def test_ground_truth_uses_agreement_then_resolution(tmp_path):
    def write(name, rows, header):
        with (tmp_path / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    write("key.csv", [["P001", "s1"], ["P002", "s2"], ["P003", "s3"]], ["packet", "solution_id"])
    write("sheet_A.csv", [["P001", "pass", 3, ""], ["P002", "fail", 3, ""], ["P003", "pass", 2, ""]],
          ["packet", "label", "confidence", "notes"])
    write("sheet_B.csv", [["P001", "pass", 3, ""], ["P002", "pass", 1, ""], ["P003", "fail", 2, ""]],
          ["packet", "label", "confidence", "notes"])
    write("resolved.csv", [["P002", "fail", "spec forbids string SQL"]], ["packet", "label", "reason"])
    truth, stats = analyze.ground_truth(tmp_path)
    assert truth == {"s1": True, "s2": False}
    assert stats["unresolved"] == 1 and stats["double_labelled"] == 3


# ---------------------------------------------------------------- judge
def test_parse_verdict_handles_prose_and_fences():
    assert judge_mod.parse_verdict('Sure.\n```json\n{"verdict": "PASS", "reason": "ok"}\n```') == (True, "ok")
    assert judge_mod.parse_verdict('{"verdict": "fail", "reason": "breaks sorting"}')[0] is False
    assert judge_mod.parse_verdict("I think it is fine")[0] is None


def test_judge_caches_answers(tmp_path, monkeypatch):
    calls = []

    class Reply:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"verdict": "pass", "reason": "meets spec"}'}}], "usage": {}}

    monkeypatch.setattr(judge_mod.httpx, "post", lambda *a, **k: calls.append(1) or Reply())
    j = judge_mod.Judge("m", "http://judge.invalid/v1", "NO_KEY", cache=tmp_path / "cache.jsonl")
    assert j.judge("prompt")["verdict"] is True
    assert judge_mod.Judge("m", "http://judge.invalid/v1", "NO_KEY", cache=tmp_path / "cache.jsonl").judge("prompt")["verdict"] is True
    assert len(calls) == 1  # second judge read the cache


# ---------------------------------------------------------------- collection and blind export
def _episode(task, ok=True, info=None, nodes=None):
    return {"task": {"data": {"name": task}}, "ok": ok,
            "traces": [{"ok": ok, "info": info or {}, "nodes": nodes or []}]}


def test_collect_patches_workflows_and_skips(tmp_path):
    patches = tmp_path / "secops_gym_patches--qwen--qwen3.8-27b--bash--abc"
    patches.mkdir()
    rows = [
        _episode("orders_pagination_004", info={"secops_gym": {"final_app_files": {"app/main.py": "x"}, "tests_modified": []}}),
        _episode("orders_pagination_004"),           # older run: no final code
        _episode("tiered_pricing_010", ok=False),    # provider error
    ]
    (patches / "traces.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    workflows = tmp_path / "secops_gym_workflows--openai--gpt-oss-120b--secops_gym_workflows--def"
    workflows.mkdir()
    nodes = [
        {"message": {"role": "assistant", "tool_calls": [{"id": "c1", "name": "issue_refund", "arguments": '{"payment_id": 2, "reason": "dup"}'}]}},
        {"message": {"role": "tool", "tool_call_id": "c1", "content": '{"payment_id": 2}'}},
    ]
    (workflows / "traces.jsonl").write_text(json.dumps(_episode("duplicate_webhook_refunds_101", nodes=nodes)))

    solutions, skipped = collect([patches, workflows])
    assert [s["kind"] for s in solutions] == ["patch", "workflow"]
    assert solutions[0]["model"] == "qwen/qwen3.8-27b" and solutions[1]["model"] == "openai/gpt-oss-120b"
    assert solutions[1]["calls"] == [{"tool": "issue_refund", "args": {"payment_id": 2, "reason": "dup"}, "result": '{"payment_id": 2}'}]
    assert skipped == {"no_final_code_in_trace": 1, "provider_or_runtime_error": 1}


def test_packets_are_blind(tmp_path):
    solutions = [
        {"solution_id": "abc:duplicate_webhook_refunds_101:0", "kind": "workflow", "task": "duplicate_webhook_refunds_101",
         "model": "qwen/qwen3.8-27b", "calls": [{"tool": "sql_query", "args": {"query": "SELECT 1"}, "result": "[]"}]},
    ]
    labels.export(solutions, tmp_path)
    packet = (tmp_path / "packets" / "P001.md").read_text(encoding="utf-8")
    for leak in ("qwen", "abc:", "V1", "V3", "verdict", "solved"):
        assert leak not in packet
    with pytest.raises(SystemExit):
        labels.export(solutions, tmp_path)  # never overwrite existing labels


# ---------------------------------------------------------------- known-answer corpus
def test_corpus_labels_gold_right_and_every_exploit_wrong():
    from audit import corpus

    records = corpus.patch_records() + corpus.workflow_records()
    gold = [r for r in records if r["source"] == "gold"]
    wrong = [r for r in records if not r["known_label"]]
    assert len(gold) == len(list(corpus.TASKS.glob("*/task.yaml"))) + len(list(corpus.WORKFLOWS.glob("*/task.yaml")))
    assert all(r["known_label"] for r in gold)
    assert {r["source"] for r in wrong} >= {"exploit:edit_public_tests", "exploit:edit_seed"}
    edited = next(r for r in records if r["source"] == "exploit:edit_public_tests")
    assert edited["tests_modified"] and all(p.startswith("tests_public/") for p in edited["tests_modified"])


def test_analyze_counts_wrong_and_right_from_known_labels(tmp_path):
    corpus_file = tmp_path / "corpus.jsonl"
    corpus_file.write_text("".join(json.dumps({"solution_id": s, "known_label": l}) + "\n"
                                   for s, l in [("a", True), ("b", False), ("c", False)]))
    verdicts = [{"solution_id": s, "V1": v1, "V3": v3} for s, v1, v3 in
                [("a", "True", "True"), ("b", "True", "False"), ("c", "False", "False")]]
    rows = {r["verifier"]: r for r in analyze.analyze(verdicts, analyze.known_truth(corpus_file))}
    assert (rows["V1"]["wrong"], rows["V1"]["right"], rows["V1"]["fpr"]) == (2, 1, 0.5)
    assert rows["V3"]["fpr"] == 0.0
    assert "Known-answer solutions" in analyze.report(list(rows.values()), {"known": 3})
