"""Prompts for single-turn training: the task, the service code and public tests, and the answer format."""

from __future__ import annotations

from pathlib import Path

import yaml

SYSTEM = "You are a careful backend engineer. You fix bugs in Python services."

FORMAT = """Reply with the complete new content of app/main.py in one ```python code block. Change only \
app/main.py; the tests, the seed data and app/db.py stay as they are."""


def prompt(task_dir: Path) -> list[dict]:
    task = yaml.safe_load((task_dir / "task.yaml").read_text())
    files = []
    for path in sorted([*(task_dir / "app").rglob("*.py"), *(task_dir / "tests_public").rglob("*.py")]):
        rel = path.relative_to(task_dir).as_posix()
        if path.stat().st_size and "__pycache__" not in rel:
            files.append(f"<file path=\"{rel}\">\n{path.read_text()}</file>")
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{task['prompt'].strip()}\n\n" + "\n\n".join(files) + f"\n\n{FORMAT}"},
    ]


def records(task_dirs: list[Path]) -> list[dict]:
    """One record per task: {"prompt": chat messages, "task_dir": path}."""
    out = []
    for folder in task_dirs:
        for spec in sorted(Path(folder).resolve().glob("*/task.yaml")):
            out.append({"prompt": prompt(spec.parent), "task_dir": str(spec.parent)})
    return out
