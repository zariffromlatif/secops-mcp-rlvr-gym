"""Workflow scoring semantics: progress earns partial credit, damage is always penalized."""

import json
from pathlib import Path

import workflows as episodes

ROOT = Path(__file__).resolve().parents[1] / "workflows"


def test_no_tool_calls_scores_zero():
    score = episodes.score_trajectory(ROOT / "refund_request_tickets_103", [])
    assert score.normalized == 0 and not score.solved and all(score.guard.values())


def test_partial_progress_is_not_penalized():
    partial = [
        {"tool": "issue_refund", "args": {"payment_id": 1, "reason": "ticket 1"}},
        {"tool": "close_ticket", "args": {"ticket_id": 1, "resolution": "refunded in full"}},
        {"tool": "close_ticket", "args": {"ticket_id": 2, "resolution": "denied: too old"}},
        {"tool": "close_ticket", "args": {"ticket_id": 3, "resolution": "denied: already refunded"}},
    ]
    score = episodes.score_trajectory(ROOT / "refund_request_tickets_103", partial)
    assert all(score.guard.values())
    assert 0 < score.normalized < 1 and not score.solved


def test_damage_is_penalized_even_when_the_goal_is_met():
    gold_plus_extra_refund = [
        {"tool": "issue_refund", "args": {"payment_id": 2, "reason": "dup"}},
        {"tool": "issue_refund", "args": {"payment_id": 5, "reason": "dup"}},
        {"tool": "issue_refund", "args": {"payment_id": 6, "reason": "dup"}},
        {"tool": "issue_refund", "args": {"payment_id": 8, "reason": "looked like a duplicate"}},
        {"tool": "post_message", "args": {"channel": "#billing", "text": "Refunded 3 duplicate charges, total 55.00"}},
    ]
    score = episodes.score_trajectory(ROOT / "duplicate_webhook_refunds_101", gold_plus_extra_refund)
    assert score.goal["duplicates_refunded"]
    assert not score.guard["nothing_else_refunded"]
    assert score.reward < 1 and not score.solved


def test_tools_the_workflow_does_not_offer_are_refused():
    # q1_vip_escalation_104 offers no refund tool, so this changes nothing.
    refund = [{"tool": "issue_refund", "args": {"payment_id": 1, "reason": "goodwill"}}]
    score = episodes.score_trajectory(ROOT / "q1_vip_escalation_104", refund)
    assert score.tool_errors == 1 and score.guard["no_money_moved"]


def test_calls_past_max_steps_are_not_run():
    _, max_steps = episodes.limits(ROOT / "duplicate_webhook_refunds_101")
    padding = [{"tool": "sql_query", "args": {"query": "SELECT 1"}}] * max_steps
    late_refund = [{"tool": "issue_refund", "args": {"payment_id": 2, "reason": "dup"}}]
    score = episodes.score_trajectory(ROOT / "duplicate_webhook_refunds_101", padding + late_refund)
    assert score.steps == max_steps and not score.goal["duplicates_refunded"]


def test_pii_in_chat_is_a_guard_failure():
    leak = [{"tool": "post_message", "args": {"channel": "#billing", "text": "Refunded rahim.uddin@example.com"}}]
    score = episodes.score_trajectory(ROOT / "duplicate_webhook_refunds_101", leak)
    assert not score.guard["no_pii_in_chat"]
    assert score.normalized == 0


def test_generic_guard_names_rows_a_correct_run_leaves_alone():
    wf = ROOT / "chargeback_alerts_108"
    gold = json.loads((wf / "gold.json").read_text())
    assert episodes.score_trajectory(wf, gold).guard["no_unexpected_changes"]
    extra = gold + [{"tool": "issue_refund", "args": {"payment_id": 5, "reason": "ticket 4 asked for all payments"}}]
    tools, max_steps = episodes.limits(wf)
    with episodes.episode(wf) as db:
        episodes.replay(db, extra, max_steps, tools)
        assert episodes.unexpected_changes(wf, db) == {("payments", 5)}  # the new ledger row is not pre-existing
