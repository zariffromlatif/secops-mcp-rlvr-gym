"""Patch application: touched paths are relative to the task, and only app/ may be edited."""

import difflib
import tempfile
from pathlib import Path

import score_patch as sp

TASK = Path(__file__).resolve().parents[1] / "tasks" / "revenue_double_count_007"


def patch_for(rel: str, old: str, new: str) -> str:
    before = (TASK / rel).read_text()
    after = before.replace(old, new)
    assert after != before
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{rel}", f"b/{rel}"))


def test_touched_paths_are_relative_to_the_task_inside_the_repo():
    # Scratch dirs sit under the repo's .tmp/, where git would otherwise report repo-relative paths.
    sp.TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
        work = Path(tmp)
        sp.prepare_workdir(TASK, work)
        ok, touched = sp.apply_patch(work, TASK / "gold.patch")
    assert ok and touched == ["app/main.py"]


def test_editing_seed_data_fails_format_without_running_tests(tmp_path):
    # Collapsing multi-payment rows would make the buggy JOIN look correct.
    patch = tmp_path / "seed.patch"
    patch.write_text(patch_for("seed.sql", "    (2, 2000), (2, 3000),\n", "    (2, 5000),\n"))
    r = sp.score_patch(TASK, patch)
    assert r.format < 0 and r.regression == r.security == 0 and not r.solved
    assert r.notes == ["modified a file outside app/: seed.sql"]
