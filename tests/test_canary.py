"""Every answer file in tasks/ and workflows/ carries the canary; no file the agent sees does."""

from verifier.canary import CANARY, ROOT, answer_files, missing


def test_answer_files_carry_the_canary():
    assert len(answer_files(ROOT / "tasks")) >= 17 * 5 and len(answer_files(ROOT / "workflows")) >= 8
    assert missing(ROOT / "tasks", ROOT / "workflows") == []


def test_files_the_agent_sees_do_not():
    for folder in ("tasks", "workflows"):
        for spec in (ROOT / folder).glob("*/task.yaml"):
            seen = [spec, *spec.parent.glob("seed.sql"), *spec.parent.glob("app/**/*.py"),
                    *spec.parent.glob("tests_public/**/*.py")]
            assert not [p for p in seen if CANARY in p.read_text()]
