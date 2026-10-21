"""secops-gym-workflows: operate mock company tools over MCP; graded on final DB state.

The agent gets only the MCP tools (default harness: the tool-only chat loop, no
shell), so every change goes through a validated tool call. The score is the
fraction of hidden GOAL checks passed minus 0.5 per failed GUARD check (wrong
refunds, leaked PII, touched tickets...). Requires a reachable Postgres
(DATABASE_URL, default postgresql+psycopg://gym:gym@localhost:5433/gym).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

import verifiers.v1 as vf
from verifiers.v1.harnesses.null.harness import NullHarness
from secops_gym_workflows._vendor import workflows as episodes
from secops_gym_workflows.toolset import WORKFLOWS, CompanyToolset, WorkflowState


class WorkflowData(vf.TaskData):
    workflow_id: str


class WorkflowTaskConfig(vf.TaskConfig):
    tools: vf.ToolsetConfig = vf.ToolsetConfig()


class WorkflowTask(vf.Task[WorkflowData, WorkflowState, WorkflowTaskConfig]):
    NEEDS_CONTAINER = False

    @property
    def key(self) -> str:
        return self.data.workflow_id

    @classmethod
    def toolsets(cls, config: WorkflowTaskConfig) -> list[vf.Toolset]:
        return [CompanyToolset(config.tools)]

    @vf.metric
    async def breakdown(self, trace: vf.Trace) -> dict:
        db_name = trace.state.db_name
        if db_name is None:  # no tool was ever called: nothing done, nothing damaged
            checks = episodes.load_checks(WORKFLOWS / self.data.workflow_id)
            score = episodes.WorkflowScore(
                goal={name: False for name in checks.GOAL}, guard={name: True for name in checks.GUARD}
            )
        else:
            try:
                score = episodes.check_state(WORKFLOWS / self.data.workflow_id, db_name)
            finally:
                episodes.drop_episode_db(db_name)
        trace.state.score = score.normalized
        # Saved with the trace; the tool calls themselves are already in it, so episodes can be replayed.
        trace.info["secops_gym"] = {"goal": score.goal, "guard": score.guard, "reward": score.reward}
        metrics = {f"goal_{k}": float(v) for k, v in score.goal.items()}
        metrics |= {f"guard_{k}": float(v) for k, v in score.guard.items()}
        return metrics | {"solved": float(score.solved)}

    @vf.reward(weight=1.0)
    async def reward(self, trace: vf.Trace) -> float:
        return float(trace.state.score)

    async def validate(self, runtime: vf.Runtime) -> bool:
        """Gold check: replay the recorded gold trajectory in a fresh episode."""
        wf_dir = WORKFLOWS / self.data.workflow_id
        gold = json.loads((wf_dir / "gold.json").read_text())
        return episodes.score_trajectory(wf_dir, gold).solved


class WorkflowTasksetConfig(vf.TasksetConfig):
    task: WorkflowTaskConfig = WorkflowTaskConfig()


class WorkflowTaskset(vf.Taskset[WorkflowTask, WorkflowTasksetConfig]):
    def load(self):
        for spec_path in sorted(WORKFLOWS.glob("*/task.yaml")):
            spec = yaml.safe_load(spec_path.read_text())
            yield WorkflowTask(
                WorkflowData(workflow_id=spec["id"], name=spec["id"], prompt=spec["prompt"].strip()),
                self.config.task,
            )


class WorkflowHarness(NullHarness):
    """Default harness for this taskset: tool-only chat loop, no shell or code execution."""
