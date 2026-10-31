"""Re-score one solution with each deterministic verifier.

Patch tasks (the solution is the agent's final app/ files):
    V1  public tests only: what the agent can see and run
    V2  public + hidden tests: regression and target
    V3  multi-signal (ours): V2 + static analysis + format and tamper gates

Workflows (the solution is the agent's tool calls, replayed in a fresh episode):
    V1  goal checks only: the requested outcome happened
    V3  goal + guard checks: and nothing else was damaged

There is no workflow V2. V4, the LLM judge, is in judge.py.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

from audit import ROOT  # noqa: F401  (puts runtime/ on sys.path)
import score_patch as sp
import workflows as episodes
from sandbox import run_episode
from verifier.gates import score

TASKS = ROOT / "tasks"
WORKFLOWS = ROOT / "workflows"


def _passed(counts: tuple[int, int]) -> bool:
    passed, total = counts
    return total > 0 and passed == total


def _sum(counts: list[tuple[int, int]]) -> tuple[int, int]:
    return (sum(c[0] for c in counts), sum(c[1] for c in counts))


def write_app(work: Path, app_files: dict[str, str]) -> None:
    """Replace the Python files of work/app with the solution's. Solutions record only Python files,
    so the task's other app files (e.g. stored attachments) are kept as the task ships them."""
    for path in (work / "app").rglob("*.py"):
        path.unlink()
    for rel, source in app_files.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def rescore_patch(task_id: str, app_files: dict[str, str], tests_modified=(), sandbox: str = "docker") -> dict:
    task_dir = TASKS / task_id
    spec = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))["scoring"]
    groups = {
        "public": ["tests_public"],
        "hidden_regression": [t for t in spec["regression"] if t != "tests_public"],
        "target": spec.get("security") or spec["target"],
    }
    sp.TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit-", dir=sp.TMP_ROOT) as tmp:
        work = Path(tmp)
        sp.prepare_workdir(task_dir, work)
        write_app(work, app_files)
        shutil.copytree(task_dir / "hidden", work / "hidden")

        if sandbox in ("docker", "warm"):
            flat = [t for targets in groups.values() for t in targets]
            results = iter(run_episode(work, flat, warm=sandbox == "warm"))
            counts = {g: _sum([next(results) for _ in targets]) for g, targets in groups.items()}
        else:
            counts = {g: sp.run_group(work, targets) for g, targets in groups.items()}

    breakdown = score(
        changed_files=app_files,
        touched_paths=list(tests_modified) + list(app_files),
        app_files=app_files,
        regression=_sum([counts["public"], counts["hidden_regression"]]),
        security=counts["target"],
    )
    v2 = all(_passed(c) for g, c in counts.items() if groups[g])
    return {
        "counts": {g: list(c) for g, c in counts.items()},
        "notes": breakdown.notes,
        "verdicts": {"V1": _passed(counts["public"]), "V2": v2, "V3": breakdown.solved},
    }


def rescore_workflow(workflow_id: str, trajectory: list[dict]) -> dict:
    result = episodes.score_trajectory(WORKFLOWS / workflow_id, trajectory)
    return {
        "goal": result.goal,
        "guard": result.guard,
        "verdicts": {"V1": all(result.goal.values()), "V3": result.solved},
    }


def original_app_files(task_id: str) -> dict[str, str]:
    app = TASKS / task_id / "app"
    return {f"app/{p.relative_to(app).as_posix()}": p.read_text(encoding="utf-8") for p in sorted(app.rglob("*.py"))}
