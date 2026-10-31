"""Known-answer solutions for the audit: every verifier's error rates without waiting for human labels.

Each record has the same shape as audit.collect's, plus `known_label` and `source`:
    patch tasks   gold.patch -> pass; every exploits/*.patch -> fail (wrong by construction)
    workflows     gold.json -> pass; every bad*.json -> fail

    python -m audit.corpus --out results/audit/corpus.jsonl
    python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv
    python -m audit.analyze results/audit/corpus_verdicts.csv --known results/audit/corpus.jsonl

The exploits are, by design, blocked by V3 (CI fails otherwise), so V3's false-positive rate here
is zero by construction; the corpus measures how the other verifiers (public tests, public +
hidden tests, the LLM judges) fare on wrong solutions an agent could plausibly produce.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from audit import ROOT
import score_patch as sp

TASKS = ROOT / "tasks"
WORKFLOWS = ROOT / "workflows"


def _patched_app(task_dir: Path, patch: Path) -> tuple[dict[str, str], list[str]]:
    """The app files after applying `patch`, and the test files it touched."""
    sp.TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="corpus-", dir=sp.TMP_ROOT) as tmp:
        work = Path(tmp)
        sp.prepare_workdir(task_dir, work)
        ok, touched = sp.apply_patch(work, patch)
        if not ok:
            raise ValueError(f"{patch} does not apply")
        app = {f"app/{p.relative_to(work / 'app').as_posix()}": p.read_text() for p in sorted((work / "app").rglob("*.py"))}
    return app, [t for t in touched if t.startswith("tests_public/")]


def patch_records() -> list[dict]:
    records = []
    for task_dir in sorted(p.parent for p in TASKS.glob("*/task.yaml")):
        for patch, label, source in [(task_dir / "gold.patch", True, "gold")] + [
            (p, False, f"exploit:{p.stem}") for p in sorted(task_dir.glob("exploits/*.patch"))
        ]:
            app, tests_modified = _patched_app(task_dir, patch)
            records.append({
                "solution_id": f"corpus:{task_dir.name}:{source}", "kind": "patch", "task": task_dir.name,
                "model": "reference", "run": "corpus", "app_files": app, "tests_modified": tests_modified,
                "known_label": label, "source": source,
            })
    return records


def workflow_records() -> list[dict]:
    records = []
    for wf_dir in sorted(p.parent for p in WORKFLOWS.glob("*/task.yaml")):
        for path, label in [(wf_dir / "gold.json", True)] + [(p, False) for p in sorted(wf_dir.glob("bad*.json"))]:
            source = "gold" if label else f"bad:{path.stem}"
            calls = [{"tool": c["tool"], "args": c.get("args", {})} for c in json.loads(path.read_text())]
            records.append({
                "solution_id": f"corpus:{wf_dir.name}:{source}", "kind": "workflow", "task": wf_dir.name,
                "model": "reference", "run": "corpus", "calls": calls, "known_label": label, "source": source,
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "audit" / "corpus.jsonl")
    args = parser.parse_args()
    records = patch_records() + workflow_records()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    wrong = sum(not r["known_label"] for r in records)
    print(f"{len(records)} known-answer solutions ({wrong} wrong, {len(records) - wrong} right) -> {args.out}")


if __name__ == "__main__":
    main()
