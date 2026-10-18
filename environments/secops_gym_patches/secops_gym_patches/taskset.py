"""secops-gym-patches: fix a bug in a small FastAPI + Postgres service.

Each rollout gets a container with the service in /app and a local Postgres. The
agent (bash harness by default) edits /app/app as the unprivileged `agent` user.
Scoring copies the agent's app/, serves it as `nobody`, and runs pristine public
tests plus hidden tests against it over HTTP (see image/score_box.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

import verifiers.v1 as vf
from secops_gym_patches._vendor import gates

PKG = Path(__file__).resolve().parent
TASKS = PKG / "data" / "tasks"
BOX = "/opt/gym"
DEFAULT_IMAGE = "secops-gym-task:0.1"

INSTRUCTIONS = """

---
The service is in /app (code in /app/app). A Postgres database is already running locally.
Run the public tests with:  cd /app && python -m pytest -q tests_public
Fix the problem by editing files under /app/app only. Do not modify the tests.
When you are done, stop and reply with a one-line summary of your fix."""


def _files(root: Path, *names: str) -> dict[str, bytes]:
    out = {}
    for name in names:
        path = root / name
        if path.is_file():
            out[name] = path.read_bytes()
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    out[f.relative_to(root).as_posix()] = f.read_bytes()
    return out


async def _run(runtime: vf.Runtime, argv: list[str]) -> vf.ProgramResult:
    result = await runtime.run(argv, {})
    if result.exit_code != 0:
        raise vf.TaskError(f"{' '.join(argv)} failed ({result.exit_code}): {result.stderr[-500:]}")
    return result


class PatchData(vf.TaskData):
    task_id: str
    category: str = ""


class PatchState(vf.State):
    gym: dict = {}


class PatchTask(vf.Task[PatchData, PatchState]):
    NEEDS_CONTAINER = True

    @property
    def key(self) -> str:
        return self.data.task_id

    @property
    def task_dir(self) -> Path:
        return TASKS / self.data.task_id

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        for rel, content in _files(self.task_dir, "app", "tests_public", "seed.sql").items():
            await runtime.write(f"/app/{rel}", content)
        await _run(runtime, ["sh", f"{BOX}/start_db.sh"])
        await _run(runtime, ["chown", "-R", "agent:agent", "/app"])

    async def _score(self, runtime: vf.Runtime) -> gates.RewardBreakdown:
        scoring = yaml.safe_load((self.task_dir / "task.yaml").read_text())["scoring"]
        for rel, content in _files(self.task_dir, "hidden").items():
            await runtime.write(f"{BOX}/task/{rel}", content)
        originals = {
            rel: content.decode()
            for rel, content in _files(self.task_dir, "tests_public", "seed.sql").items()
        }
        spec = {
            "regression": scoring["regression"],
            "security": scoring.get("security") or scoring["target"],
            "originals": originals,
        }
        await runtime.write(f"{BOX}/task/spec.json", json.dumps(spec).encode())
        result = await _run(runtime, ["python", f"{BOX}/score_box.py", f"{BOX}/task/spec.json"])
        out = json.loads(result.stdout.strip().splitlines()[-1])
        return gates.score(
            changed_files=out["app_files"],
            touched_paths=out["tests_modified"] + list(out["app_files"]),
            app_files=out["app_files"],
            regression=tuple(out["regression"]),
            security=tuple(out["security"]),
        )

    @vf.metric
    async def breakdown(self, trace: vf.Trace, runtime: vf.Runtime) -> dict:
        r = await self._score(runtime)
        trace.state.gym = {"normalized": r.normalized, "notes": r.notes}
        return {
            "gate_format": r.format,
            "gate_regression": r.regression,
            "gate_target": r.security,
            "gate_static": r.static,
            "solved": float(r.solved),
        }

    @vf.reward(weight=1.0)
    async def reward(self, trace: vf.Trace) -> float:
        return float(trace.state.gym.get("normalized", 0.0))

    async def validate(self, runtime: vf.Runtime) -> bool:
        """Gold check: apply the reference patch to the set-up box and require a full solve."""
        await runtime.write("/tmp/gold.patch", (self.task_dir / "gold.patch").read_bytes())
        applied = await runtime.run(["sh", "-c", "cd /app && patch -p1 -i /tmp/gold.patch"], {})
        if applied.exit_code != 0:
            return False
        return (await self._score(runtime)).solved


class PatchTasksetConfig(vf.TasksetConfig):
    image: str = DEFAULT_IMAGE
    """Task image; build it with scripts/build_task_image.sh or pull a published tag."""
    categories: list[str] = []
    """Only load tasks in these categories (e.g. ["security"]); empty loads all."""
    task: vf.TaskConfig = vf.TaskConfig()


class PatchTaskset(vf.Taskset[PatchTask, PatchTasksetConfig]):
    def load(self):
        for spec_path in sorted(TASKS.glob("*/task.yaml")):
            spec = yaml.safe_load(spec_path.read_text())
            category = "security" if "security" in spec["scoring"] else spec.get("category", "")
            if self.config.categories and category not in self.config.categories:
                continue
            yield PatchTask(
                PatchData(
                    task_id=spec["id"],
                    name=spec["id"],
                    category=category,
                    prompt=spec["prompt"].strip() + INSTRUCTIONS,
                    image=self.config.image,
                    workdir="/app",
                    agent_user="agent",
                    artifacts=[vf.Artifact(source="/app/app")],  # what an isolated verifier restores
                ),
                self.config.task,
            )
