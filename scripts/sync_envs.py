"""Copy tasks, workflows and shared code into the environment packages.

Run after changing anything under tasks/, workflows/, verifier/ or runtime/,
and before building or pushing an environment:

    uv run python scripts/sync_envs.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def replace_tree(src: Path, dst: Path) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=IGNORE)


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


patches = ROOT / "environments/secops_gym_patches/secops_gym_patches"
replace_tree(ROOT / "tasks", patches / "data/tasks")
(patches / "data/tasks/README.md").unlink(missing_ok=True)
copy(ROOT / "verifier/gates.py", patches / "_vendor/gates.py")
(patches / "_vendor/__init__.py").touch()
copy(ROOT / "runtime/requirements-sandbox.txt", patches / "image/requirements.txt")

workflows = ROOT / "environments/secops_gym_workflows/secops_gym_workflows"
replace_tree(ROOT / "workflows", workflows / "data/workflows")
copy(ROOT / "runtime/mcp_tools.py", workflows / "_vendor/mcp_tools.py")
copy(ROOT / "runtime/workflows.py", workflows / "_vendor/workflows.py")
(workflows / "_vendor/__init__.py").touch()

print("synced environments")
