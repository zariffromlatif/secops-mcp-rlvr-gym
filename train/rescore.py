"""Score recorded answers again in an isolated sandbox, and list every answer whose reward changes.

Local mode (no Docker, e.g. on a PC without admin rights) imports each answer into the test process,
so an answer could earn its reward with an in-process trick instead of a fix. After such a run, on any
machine with Docker:

    python -m train.rescore results/train                  # every samples.jsonl below the folder
    python -m train.rescore results/train --passing-only   # only answers recorded as passing every test or solved

Each distinct (task, answer) is scored once in the warm sandbox and compared with what was recorded.
The report (--out, default results/train/rescore.md) gives per file how many answers were recorded
higher than they score in isolation ("inflated": what an in-process trick would show) or lower
("deflated": flaky tests, usually), and lists them. Exit status 1 if any answer is inflated.

Tasks are found by name in tasks/, tasks_generated/ and tasks_private/; answers to a task that is not
there are counted as skipped. The campaign's generated tasks are not in the repository; rebuild them
first, the held-out ones with the campaign's secret (the line in ~/.secops-gym-heldout-secret):

    python -m factory.generate --count 3 --seed 1 --secret "" --out tasks_generated
    GYM_FACTORY_SECRET=<secret> python -m factory.generate --count 3 --out tasks_private

Scores are cached next to the report (<out stem>-<sandbox>.jsonl), so an interrupted run continues.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from train.grpo import REWARDS
from train.scoring import ROOT, Scorer, extract_main

TASK_DIRS = ["tasks", "tasks_generated", "tasks_private"]
TOLERANCE = 1e-3  # recorded rewards are rounded to 4 decimals


def load(paths: list[Path]) -> list[dict]:
    """Every recorded answer, from the samples.jsonl files given or found below the folders given."""
    files = []
    for path in paths:
        files += sorted(path.rglob("samples.jsonl")) if path.is_dir() else [path]
    rows = []
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row.get("answer"), str):
                    rows.append({**row, "file": str(file)})
    return rows


def key(row: dict) -> str:
    return f"{row['task']}:{hashlib.sha256(row['answer'].encode()).hexdigest()}"


def passing(row: dict) -> bool:
    return bool(row["solved"]) or row["v2"] >= 1 - TOLERANCE


def compare(recorded: dict, isolated: dict) -> str:
    """'inflated' if the recorded score is higher anywhere, else 'deflated' if lower anywhere, else 'same'."""
    if any(recorded[k] > isolated[k] + TOLERANCE for k in REWARDS) or (recorded["solved"] and not isolated["solved"]):
        return "inflated"
    if any(recorded[k] < isolated[k] - TOLERANCE for k in REWARDS) or (isolated["solved"] and not recorded["solved"]):
        return "deflated"
    return "same"


def rescore(rows: list[dict], scorer: Scorer, task_dirs: list[Path], workers: int,
            cache: Path | None = None) -> dict[str, dict]:
    """Isolated scores by key() for every row whose task is found; reuses and extends the cache."""
    done: dict[str, dict] = {}
    if cache and cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r
    todo: dict[str, tuple[Path, str]] = {}
    for row in rows:
        k = key(row)
        if k not in done and k not in todo:
            folder = next((d / row["task"] for d in task_dirs if (d / row["task"] / "task.yaml").exists()), None)
            if folder is not None:
                todo[k] = (folder, row["answer"])
    if not todo:
        return done
    print(f"re-scoring {len(todo)} distinct answers ({len(done)} cached)", flush=True)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
    fh = cache.open("a", encoding="utf-8") if cache else None
    try:
        with ThreadPoolExecutor(workers) as pool:
            futures = {pool.submit(scorer.score, folder, extract_main(answer)): k for k, (folder, answer) in todo.items()}
            for i, future in enumerate(as_completed(futures), 1):
                s = future.result()
                r = {"key": futures[future], **{k: round(s[k], 4) for k in REWARDS}, "solved": s["solved"],
                     "notes": s["notes"]}
                done[r["key"]] = r
                if fh:
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                if i % 100 == 0 or i == len(futures):
                    print(f"re-scored {i}/{len(futures)}", flush=True)
    finally:
        if fh:
            fh.close()
    return done


def render(rows: list[dict], isolated: dict[str, dict], sandbox: str, limit: int = 50) -> tuple[str, int]:
    """The report, and how many answers were inflated."""
    show = lambda r: "/".join(f"{r[k]:.2f}" for k in REWARDS) + (" solved" if r["solved"] else "")  # noqa: E731
    files: dict[str, dict] = {}
    listed = {"inflated": [], "deflated": []}
    skipped = set()
    for row in rows:
        f = files.setdefault(row["file"], {"answers": 0, "same": 0, "inflated": 0, "deflated": 0, "skipped": 0})
        f["answers"] += 1
        iso = isolated.get(key(row))
        if iso is None:
            f["skipped"] += 1
            skipped.add(row["task"])
            continue
        verdict = compare(row, iso)
        f[verdict] += 1
        if verdict != "same":
            listed[verdict].append(f"| {row['file']} | {row.get('step', '')} | {row['task']} | {show(row)} | {show(iso)} "
                                   f"| {key(row).split(':')[1][:12]} |")
    inflated = sum(f["inflated"] for f in files.values())
    lines = [f"# Recorded rewards checked in the {sandbox} sandbox", "",
             f"{len(rows)} answers in {len(files)} files, {len({key(r) for r in rows})} distinct. "
             "v1/v2/v3 as recorded during the run, then as scored again here. **Inflated**: recorded higher "
             "than here, which is what an answer exploiting a non-isolated scorer would look like. "
             "**Deflated**: recorded lower (usually a flaky test).", ""]
    if skipped:
        lines += [f"Skipped (task not found; rebuild it, see `python -m train.rescore --help`): "
                  f"{', '.join(sorted(skipped))}.", ""]
    lines += ["| file | answers | same | inflated | deflated | skipped |", "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {name} | {f['answers']} | {f['same']} | {f['inflated']} | {f['deflated']} | {f['skipped']} |"
              for name, f in files.items()]
    for verdict in ("inflated", "deflated"):
        if listed[verdict]:
            lines += ["", f"## {verdict.capitalize()} ({len(listed[verdict])}"
                      + (f", first {limit}" if len(listed[verdict]) > limit else "") + ")", "",
                      "| file | step | task | recorded v1/v2/v3 | here v1/v2/v3 | answer sha256 |",
                      "|---|---:|---|---|---|---|", *listed[verdict][:limit]]
    return "\n".join(lines) + "\n", inflated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", type=Path, nargs="+", help="samples.jsonl files, or folders to search for them")
    parser.add_argument("--sandbox", choices=["warm", "docker", "local"], default="warm",
                        help="warm or docker (isolated); local only for testing this tool")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--tasks", type=Path, nargs="+", default=[ROOT / d for d in TASK_DIRS],
                        help="folders the tasks are looked up in, by name")
    parser.add_argument("--passing-only", action="store_true",
                        help="only answers recorded as solved or passing every test (v2 = 1): the quick check")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "train" / "rescore.md")
    args = parser.parse_args(argv)

    rows = load(args.paths)
    if args.passing_only:
        rows = [r for r in rows if passing(r)]
    if not rows:
        raise SystemExit("no recorded answers found")
    cache = args.out.with_name(f"{args.out.stem}-{args.sandbox}.jsonl")
    isolated = rescore(rows, Scorer(args.sandbox, args.workers), args.tasks, args.workers, cache)
    text, inflated = render(rows, isolated, args.sandbox)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 1 if inflated else 0


if __name__ == "__main__":
    raise SystemExit(main())
