"""Episodes and scoring for MCP workflow tasks.

A workflow episode:
  1. creates a fresh database from the workflow's seed,
  2. lets an agent (or a recorded trajectory) call the mock tools as the
     unprivileged `wf_agent` role,
  3. scores the final database state with the workflow's hidden checks.

    uv run python runtime/workflows.py score workflows/duplicate_webhook_refunds_101 gold.json
    uv run python runtime/workflows.py validate
    uv run python runtime/workflows.py start workflows/duplicate_webhook_refunds_101   # for live agents
    uv run python runtime/workflows.py finish workflows/duplicate_webhook_refunds_101 <db_name>
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

RUNTIME = Path(__file__).resolve().parent
ROOT = RUNTIME.parent
sys.path.insert(0, str(RUNTIME))

from mcp_tools import BASE_SCHEMA, ToolError, call_tool  # noqa: E402

ADMIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://gym:gym@localhost:5433/gym")
AGENT_ROLE, AGENT_PASSWORD = "wf_agent", "wf_agent"
GUARD_PENALTY = 0.5


@dataclass
class WorkflowScore:
    goal: dict[str, bool] = field(default_factory=dict)
    guard: dict[str, bool] = field(default_factory=dict)
    tool_errors: int = 0
    steps: int = 0

    @property
    def reward(self) -> float:
        goal = sum(self.goal.values()) / len(self.goal)
        return goal - GUARD_PENALTY * sum(not ok for ok in self.guard.values())

    @property
    def normalized(self) -> float:
        return max(0.0, self.reward)

    @property
    def solved(self) -> bool:
        return all(self.goal.values()) and all(self.guard.values())


def _admin():
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})


def agent_url(db_name: str) -> str:
    url = make_url(ADMIN_URL).set(database=db_name, username=AGENT_ROLE, password=AGENT_PASSWORD)
    return url.render_as_string(hide_password=False)


def create_episode_db(wf_dir: Path) -> str:
    """Create and seed a fresh database; return its name."""
    name = f"wf_{uuid.uuid4().hex[:10]}"
    admin = _admin()
    with admin.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": AGENT_ROLE}).first() is None:
            conn.exec_driver_sql(
                f"CREATE ROLE {AGENT_ROLE} LOGIN PASSWORD '{AGENT_PASSWORD}' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE"
            )
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    admin.dispose()

    seed = BASE_SCHEMA + (wf_dir / "seed.sql").read_text()
    episode = create_engine(make_url(ADMIN_URL).set(database=name))
    with episode.begin() as conn:
        conn.exec_driver_sql(seed)
        conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {AGENT_ROLE}")
        conn.exec_driver_sql(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {AGENT_ROLE}")
    episode.dispose()
    return name


def drop_episode_db(name: str) -> None:
    admin = _admin()
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.dispose()


@contextlib.contextmanager
def episode(wf_dir: Path):
    name = create_episode_db(wf_dir)
    try:
        yield name
    finally:
        drop_episode_db(name)


def replay(db_name: str, trajectory: list[dict], max_steps: int) -> tuple[list[dict], int]:
    """Run recorded tool calls as the agent role. Returns per-step results and error count."""
    engine = create_engine(agent_url(db_name))
    results, errors = [], 0
    try:
        for step in trajectory[:max_steps]:
            try:
                with engine.begin() as conn:
                    results.append({"ok": True, "result": call_tool(conn, step["tool"], step.get("args", {}))})
            except ToolError as exc:
                errors += 1
                results.append({"ok": False, "error": str(exc)})
    finally:
        engine.dispose()
    return results, errors


def load_checks(wf_dir: Path):
    spec = importlib.util.spec_from_file_location(f"checks_{wf_dir.name}", wf_dir / "checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_state(wf_dir: Path, db_name: str) -> WorkflowScore:
    checks = load_checks(wf_dir)
    engine = create_engine(make_url(ADMIN_URL).set(database=db_name))
    try:
        with engine.connect() as conn:
            score = WorkflowScore(
                goal={name: bool(fn(conn)) for name, fn in checks.GOAL.items()},
                guard={name: bool(fn(conn)) for name, fn in checks.GUARD.items()},
            )
    finally:
        engine.dispose()
    return score


def score_trajectory(wf_dir: Path, trajectory: list[dict]) -> WorkflowScore:
    spec = yaml.safe_load((wf_dir / "task.yaml").read_text())
    with episode(wf_dir) as db_name:
        _, errors = replay(db_name, trajectory, spec.get("max_steps", 40))
        score = check_state(wf_dir, db_name)
    score.tool_errors, score.steps = errors, min(len(trajectory), spec.get("max_steps", 40))
    return score


def report(score: WorkflowScore) -> dict:
    return {**asdict(score), "reward": round(score.reward, 3), "normalized": round(score.normalized, 3), "solved": score.solved}


def validate() -> int:
    """gold.json must be solved, noop.json must score 0, bad*.json must not be solved."""
    failures = 0
    for spec_path in sorted((ROOT / "workflows").glob("*/task.yaml")):
        wf_dir = spec_path.parent
        gold = score_trajectory(wf_dir, json.loads((wf_dir / "gold.json").read_text()))
        noop = score_trajectory(wf_dir, json.loads((wf_dir / "noop.json").read_text()))
        bads = {p.name: score_trajectory(wf_dir, json.loads(p.read_text())) for p in sorted(wf_dir.glob("bad*.json"))}
        ok = gold.solved and gold.tool_errors == 0 and noop.normalized == 0 and not any(b.solved for b in bads.values())
        failures += not ok
        extra = "".join(f"  {name}={b.normalized:.2f}" for name, b in bads.items())
        print(f"{'PASS' if ok else 'FAIL'}  {wf_dir.name}  gold={gold.normalized:.2f}  noop={noop.normalized:.2f}{extra}")
        if not ok:
            print(f"      gold: {report(gold)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("workflow", type=Path)
    s.add_argument("trajectory", type=Path)
    sub.add_parser("validate")
    st = sub.add_parser("start")
    st.add_argument("workflow", type=Path)
    fin = sub.add_parser("finish")
    fin.add_argument("workflow", type=Path)
    fin.add_argument("db_name")
    args = parser.parse_args()

    if args.cmd == "validate":
        return validate()
    if args.cmd == "score":
        trajectory = json.loads(args.trajectory.read_text())
        print(json.dumps(report(score_trajectory(args.workflow, trajectory)), indent=2))
    elif args.cmd == "start":
        name = create_episode_db(args.workflow)
        print(f"db_name={name}\nWORKFLOW_DB_URL={agent_url(name)}")
        print(f"\nPrompt:\n{yaml.safe_load((args.workflow / 'task.yaml').read_text())['prompt']}")
    elif args.cmd == "finish":
        score = check_state(args.workflow, args.db_name)
        drop_episode_db(args.db_name)
        print(json.dumps(report(score), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
