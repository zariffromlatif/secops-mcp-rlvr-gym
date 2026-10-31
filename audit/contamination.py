"""Has a model seen this repository's answers? Two probes, through any OpenAI-compatible endpoint.

    canary   ask the model to finish the canary string (verifier/canary.py). Completing the GUID
             means the answer files were in its training data.
    recall   show the first half of each task's hidden target tests and ask for the rest. Score the
             share of the remaining distinctive lines it reproduces verbatim. The control is a
             factory task generated now with a random secret, which no model can have seen.

    uv run python -m audit.contamination --model llama-3.3-70b-versatile [--samples 5] [--out FILE]

A model with recall well above the control, or that completes the canary, should not be scored on
these tasks; use a private split (docs/contamination.md).
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.llm import Client  # noqa: E402
from factory.families import FAMILIES  # noqa: E402
from factory.generate import generate  # noqa: E402
from verifier.canary import CANARY  # noqa: E402

PREFIX, GUID = CANARY.rsplit(" ", 1)


def canary_probe(client: Client, samples: int) -> dict:
    hits = 0
    for _ in range(samples):
        reply = client.chat([{"role": "user", "content": f"Complete this line exactly, with nothing else:\n{PREFIX} "}],
                            temperature=1.0)["content"] or ""
        hits += GUID[:8] in reply
    return {"samples": samples, "completed": hits}


def distinctive(lines: list[str]) -> list[str]:
    """Lines that carry task-specific content: long enough, not imports or boilerplate."""
    return [s for s in (line.strip() for line in lines)
            if len(s) >= 25 and not s.startswith(("import ", "from ", "#", "def test_", '"""', "@pytest"))]


def recall(client: Client, name: str, source: str) -> dict:
    lines = [line for line in source.splitlines() if CANARY not in line]
    half = len(lines) // 2
    rest = distinctive(lines[half:])
    reply = client.chat([{"role": "user", "content":
                          f"This is the first half of tests/{name} from the GitHub repository "
                          "secops-mcp-rlvr-gym. Continue the file from where it stops. Reply with code only.\n\n"
                          + "\n".join(lines[:half])}], temperature=0)["content"] or ""
    said = {line.strip() for line in reply.splitlines()}
    return {"file": name, "lines": len(rest), "reproduced": sum(line in said for line in rest)}


def target_tests(task_dir: Path) -> Path:
    return next(p for p in sorted((task_dir / "hidden").glob("test_*.py")) if p.name != "test_regression_hidden.py")


def run(client: Client, samples: int) -> dict:
    tasks = [recall(client, f"{d.name}/{target_tests(d).name}", target_tests(d).read_text())
             for d in sorted(p.parent for p in (ROOT / "tasks").glob("*/task.yaml"))]
    secret = secrets.token_hex(16)
    control = []
    for family in sorted(FAMILIES):
        task_id, files = generate(family, 1, 0, secret=secret)
        rel = next(r for r in sorted(files) if r.startswith("hidden/test_") and r != "hidden/test_regression_hidden.py")
        control.append(recall(client, f"{task_id}/{Path(rel).name}", files[rel]))
    share = lambda rows: sum(r["reproduced"] for r in rows) / max(1, sum(r["lines"] for r in rows))  # noqa: E731
    return {"model": client.model, "canary": canary_probe(client, samples),
            "recall": share(tasks), "control_recall": share(control), "tasks": tasks, "control": control}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://api.groq.com/openai/v1")
    parser.add_argument("--key-var", default="GROQ_API_KEY")
    parser.add_argument("--samples", type=int, default=5, help="canary completions to sample")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run(Client(args.model, args.base_url, args.key_var), args.samples)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"canary completed {result['canary']['completed']}/{result['canary']['samples']}; "
          f"hidden-test recall {result['recall']:.1%} (control {result['control_recall']:.1%})")


if __name__ == "__main__":
    main()
