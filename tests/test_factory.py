"""Task factory: deterministic, complete task folders whose gold patch applies. No database needed."""

import subprocess

import pytest

from factory.families import FAMILIES
from factory.generate import generate
from verifier.canary import CANARY, answer_file


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_same_seed_same_task(family):
    assert generate(family, 3, 0) == generate(family, 3, 0)
    assert generate(family, 3, 0)[1] != generate(family, 3, 1)[1]


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_secret_gives_other_tasks_and_ids_that_do_not_reveal_it(family):
    public_id, public = generate(family, 3, 0)
    private_id, private = generate(family, 3, 0, secret="s3cret-value")
    assert private != public and private == generate(family, 3, 0, secret="s3cret-value")[1]
    assert "s3cret" not in private_id and private_id != public_id
    assert generate(family, 3, 0, secret="other")[1] != private


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_answer_files_carry_the_canary(family):
    _, files = generate(family, 1, 0)
    assert {rel for rel in files if answer_file(rel)} >= {"gold.patch", "hidden/test_regression_hidden.py",
                                                          "exploits/edit_seed.patch"}
    for rel, content in files.items():
        assert (CANARY in content) == answer_file(rel), rel


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_task_folder_is_complete_and_gold_applies(family, tmp_path):
    task_id, files = generate(family, 1, 0)
    for rel, content in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(content)
    assert {"task.yaml", "app/main.py", "app/db.py", "seed.sql", "gold.patch", "noop.patch",
            "exploits/edit_public_tests.patch", "exploits/edit_seed.patch"} <= set(files)
    assert any(rel.startswith("hidden/test_") and rel != "hidden/test_regression_hidden.py" for rel in files)
    assert f"id: {task_id}" in files["task.yaml"] and f"family: {family}" in files["task.yaml"]
    applied = subprocess.run(["git", "apply", "--check", "gold.patch"], cwd=tmp_path, capture_output=True,
                             env={"GIT_CEILING_DIRECTORIES": str(tmp_path.parent), "PATH": "/usr/bin:/bin"})
    assert applied.returncode == 0, applied.stderr
