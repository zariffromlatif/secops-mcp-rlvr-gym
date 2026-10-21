"""Verifier audit: re-score agent solutions with each verifier and compare against human labels.

    python -m audit.collect  <eval run dirs...> --out results/audit/solutions.jsonl
    python -m audit.verify   results/audit/solutions.jsonl --out results/audit/verdicts.csv [--judge-model ...]
    python -m audit.labels   results/audit/solutions.jsonl --out results/audit/labeling
    python -m audit.analyze  results/audit/verdicts.csv results/audit/labeling
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "runtime"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
