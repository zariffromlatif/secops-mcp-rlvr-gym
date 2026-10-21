"""Multi-gate reward for security remediation tasks.

Each gate returns a float. `score` combines them into a total plus a per-gate
breakdown so training logs and later analysis can see which gate moved.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

FORMAT_FAIL = -0.5
FORMAT_OK = 0.2
REGRESSION_MAX = 0.8
SECURITY_MAX = 1.5
STATIC_MAX = 0.5
TOTAL_MAX = FORMAT_OK + REGRESSION_MAX + SECURITY_MAX + STATIC_MAX

SQL_SINKS = {"execute", "text", "exec_driver_sql", "raw"}


@dataclass
class RewardBreakdown:
    format: float = 0.0
    regression: float = 0.0
    security: float = 0.0
    static: float = 0.0
    notes: list[str] = field(default_factory=list)
    solved: bool = False

    @property
    def total(self) -> float:
        return self.format + self.regression + self.security + self.static

    @property
    def normalized(self) -> float:
        return max(0.0, self.total) / TOTAL_MAX


def format_gate(changed_files: dict[str, str], touched_paths: list[str]) -> tuple[float, list[str]]:
    """Patch must parse as Python and must not modify any test files."""
    notes = []
    for path in touched_paths:
        if path.startswith(("tests_public/", "hidden/")) or "/tests" in path:
            notes.append(f"modified test file: {path}")
    for path, source in changed_files.items():
        if not path.endswith(".py"):
            continue
        try:
            ast.parse(source)
        except SyntaxError as exc:
            notes.append(f"syntax error in {path}: {exc.msg}")
    return (FORMAT_FAIL if notes else FORMAT_OK), notes


def regression_gate(passed: int, total: int) -> float:
    """Fraction of functional tests passing, scaled to the gate weight."""
    return REGRESSION_MAX * passed / total if total else 0.0


def security_gate(passed: int, total: int) -> float:
    """Fraction of hidden security tests passing. All-or-nothing would starve GRPO early on."""
    return SECURITY_MAX * passed / total if total else 0.0


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "format"
    return False


def find_unsafe_sql(source: str) -> list[int]:
    """Line numbers where a SQL sink receives a string built at runtime."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in SQL_SINKS and _is_dynamic_string(node.args[0]):
            lines.append(node.lineno)
    return lines


def static_gate(app_files: dict[str, str]) -> tuple[float, list[str]]:
    """Scans the final state of the app code, not just the diff, so unpatched flaws still count."""
    notes = []
    for path, source in app_files.items():
        if path.endswith(".py"):
            for line in find_unsafe_sql(source):
                notes.append(f"dynamic SQL string at {path}:{line}")
    return (0.0 if notes else STATIC_MAX), notes


def score(
    changed_files: dict[str, str],
    touched_paths: list[str],
    app_files: dict[str, str],
    regression: tuple[int, int],
    security: tuple[int, int],
) -> RewardBreakdown:
    r = RewardBreakdown()
    r.format, notes = format_gate(changed_files, touched_paths)
    r.notes += notes
    if r.format < 0:
        return r
    r.regression = regression_gate(*regression)
    r.security = security_gate(*security)
    r.static, notes = static_gate(app_files)
    r.notes += notes
    r.solved = (
        regression[0] == regression[1] > 0
        and security[0] == security[1] > 0
        and r.static == STATIC_MAX
    )
    return r
