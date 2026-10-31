"""The warm sandbox scores like the cold one and keeps episodes apart. Needs Docker."""

import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

import score_patch as sp
import warm_sandbox as ws
from sandbox import run_episode

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "revenue_double_count_007"
PROBE = Path(__file__).resolve().parent / "warm_probe"
TARGETS = ["tests_public", "hidden/test_regression_hidden.py", "hidden/test_target.py"]

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs Docker",
)


def workdir(tmp: Path, main: Path | None = None, patch: str = "gold.patch") -> Path:
    sp.prepare_workdir(TASK, tmp)
    assert sp.apply_patch(tmp, TASK / patch)[0]
    shutil.copytree(TASK / "hidden", tmp / "hidden")
    if main:
        shutil.copy(main, tmp / "app" / "main.py")
        for checks in PROBE.glob("probe_checks*.py"):  # named so the repo's own test run skips them
            shutil.copy(checks, tmp / "hidden" / checks.name.replace("probe_checks", "test_probe"))
        secret = tmp / "host-secret.txt"  # outside app/
        secret.write_text("host secret")
        (tmp / "app" / "host_file").symlink_to(secret)  # as a patch can create
    return tmp


def pool_containers() -> set[str]:
    (pool,) = ws._all
    names = subprocess.run(["docker", "ps", "-a", "--filter", f"name={pool.id}", "--format", "{{.Names}}"],
                           capture_output=True, text=True).stdout.split()
    return {name.removeprefix(pool.id) for name in names}


@pytest.fixture(autouse=True)
def fresh_pools():
    ws.close_all()
    yield
    ws.close_all()


@pytest.mark.parametrize("task,patches", [
    ("revenue_double_count_007", ["gold.patch", "noop.patch", "exploits/merge_seed_payments.patch"]),
    ("attachment_path_traversal_015", ["gold.patch"]),  # non-Python app files (stored attachments)
])
def test_warm_scores_exactly_like_cold(task, patches):
    for patch in patches:
        cold = sp.score_patch(ROOT / "tasks" / task, ROOT / "tasks" / task / patch, "docker")
        warm = sp.score_patch(ROOT / "tasks" / task, ROOT / "tasks" / task / patch, "warm")
        assert asdict(warm) == asdict(cold), patch


def test_probe_finds_no_way_out_and_no_trace_of_earlier_episodes():
    for _ in range(3):  # later episodes look for what earlier ones left behind
        with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
            counts = run_episode(workdir(Path(tmp), PROBE / "main.py"),
                                 ["hidden/test_probe.py", "hidden/test_probe_pool.py"], warm=True)
        assert counts == [(7, 7), (1, 1)]
        # Only the warm parts and the next episode's waiting app remain; this episode's app is gone.
        containers = pool_containers()
        assert {"-db", "-test"} < containers and len(containers) == 3


def test_cold_sandbox_refuses_the_public_owner_password_too():
    with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
        assert run_episode(workdir(Path(tmp), PROBE / "main.py"), ["hidden/test_probe.py"]) == [(7, 7)]


def test_a_hung_episode_scores_zero_and_the_pool_is_replaced(tmp_path):
    hang = tmp_path / "main.py"
    hang.write_text("import time\nfrom fastapi import FastAPI\napp = FastAPI()\n\n\n"
                    "@app.get('/{path:path}')\ndef slow(path: str):\n    time.sleep(120)\n")
    with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
        assert run_episode(workdir(Path(tmp), hang), TARGETS, test_timeout=10, warm=True) == [(0, 1)] * 3
    assert ws._all == []
    with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
        assert run_episode(workdir(Path(tmp)), TARGETS, warm=True) == [(2, 2), (4, 4), (3, 3)]


def test_concurrent_episodes_get_their_own_pools():
    results = {}

    def score(name, patch):
        with tempfile.TemporaryDirectory(dir=sp.TMP_ROOT) as tmp:
            results[name] = run_episode(workdir(Path(tmp), patch=patch), TARGETS, warm=True)

    threads = [threading.Thread(target=score, args=(n, p)) for n, p in [("gold", "gold.patch"), ("noop", "noop.patch")]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {"gold": [(2, 2), (4, 4), (3, 3)], "noop": [(2, 2), (4, 4), (0, 3)]}
    assert len(ws._all) == 2
