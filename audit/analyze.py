"""Compare each verifier with the human labels: the paper's main results table.

Ground truth = the label both annotators gave; for disagreements, the label in resolved.csv.
Disagreements not yet resolved are left out and counted.

For each verifier we report, with 95% bootstrap confidence intervals over solutions:
    false-positive rate  P(verifier passes | label fail): wrong solutions it would reward
    false-negative rate  P(verifier fails  | label pass): good solutions it would punish
    accuracy

    python -m audit.analyze results/audit/verdicts.csv results/audit/labeling [--out results/audit/report.md]
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

VERIFIERS = ["V1", "V2", "V3", "V4"]


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _bool(value: str) -> bool | None:
    value = (value or "").strip().lower()
    return True if value in {"true", "pass"} else False if value in {"false", "fail"} else None


def cohens_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def rates(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs = (verifier_pass, label_pass)."""
    fp = sum(v and not g for v, g in pairs)
    tn = sum(not v and not g for v, g in pairs)
    fn = sum(not v and g for v, g in pairs)
    tp = sum(v and g for v, g in pairs)
    return {
        "n": len(pairs),
        "fpr": fp / (fp + tn) if fp + tn else float("nan"),
        "fnr": fn / (fn + tp) if fn + tp else float("nan"),
        "acc": (tp + tn) / len(pairs) if pairs else float("nan"),
    }


def bootstrap(pairs: list[tuple[bool, bool]], metric: str, samples: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    values = sorted(
        v for v in (rates([rng.choice(pairs) for _ in pairs])[metric] for _ in range(samples)) if v == v
    )
    if not values:
        return float("nan"), float("nan")
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def ground_truth(labeling: Path) -> tuple[dict[str, bool], dict]:
    key = {r["packet"]: r["solution_id"] for r in _read(labeling / "key.csv")}
    a = {r["packet"]: _bool(r["label"]) for r in _read(labeling / "sheet_A.csv")}
    b = {r["packet"]: _bool(r["label"]) for r in _read(labeling / "sheet_B.csv")}
    resolved = {}
    if (labeling / "resolved.csv").exists():
        resolved = {r["packet"]: _bool(r["label"]) for r in _read(labeling / "resolved.csv")}
    both = [p for p in key if a.get(p) is not None and b.get(p) is not None]
    truth, unresolved = {}, 0
    for p in both:
        if a[p] == b[p]:
            truth[key[p]] = a[p]
        elif resolved.get(p) is not None:
            truth[key[p]] = resolved[p]
        else:
            unresolved += 1
    stats = {
        "packets": len(key), "double_labelled": len(both), "unresolved": unresolved,
        "kappa": cohens_kappa([a[p] for p in both], [b[p] for p in both]),
    }
    return truth, stats


def analyze(verdicts: list[dict], truth: dict[str, bool]) -> list[dict]:
    rows = []
    for v in VERIFIERS:
        pairs = [(_bool(r[v]), truth[r["solution_id"]]) for r in verdicts
                 if r["solution_id"] in truth and _bool(r.get(v)) is not None]
        if not pairs:
            continue
        rows.append({"verifier": v, **rates(pairs), "fpr_ci": bootstrap(pairs, "fpr"), "fnr_ci": bootstrap(pairs, "fnr")})
    return rows


def _pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def report(rows: list[dict], stats: dict) -> str:
    lines = [
        "# Verifier audit",
        "",
        f"Packets: {stats['packets']} · labelled by both annotators: {stats['double_labelled']} · "
        f"unresolved disagreements (excluded): {stats['unresolved']} · Cohen's kappa: {stats['kappa']:.2f}",
        "",
        "| Verifier | n | False-positive rate (95% CI) | False-negative rate (95% CI) | Accuracy |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['verifier']} | {r['n']} | {_pct(r['fpr'])} ({_pct(r['fpr_ci'][0])}–{_pct(r['fpr_ci'][1])}) | "
            f"{_pct(r['fnr'])} ({_pct(r['fnr_ci'][0])}–{_pct(r['fnr_ci'][1])}) | {_pct(r['acc'])} |"
        )
    lines += ["", "V1 public tests · V2 public + hidden tests · V3 multi-signal · V4 LLM judge "
              "(workflows: V1 goal checks, V3 goal + guard checks)"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verdicts", type=Path)
    parser.add_argument("labeling", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results/audit/report.md"))
    args = parser.parse_args()
    truth, stats = ground_truth(args.labeling)
    text = report(analyze(_read(args.verdicts), truth), stats)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
