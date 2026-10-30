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


def format_gate(
    changed_files: dict[str, str], touched_paths: list[str], editable: tuple[str, ...] = ()
) -> tuple[float, list[str]]:
    """Patch must parse as Python, must not modify any test files and, when `editable` is given,
    must only touch paths under those prefixes (so seed data can't be edited either)."""
    notes = []
    for path in touched_paths:
        if path.startswith(("tests_public/", "hidden/")) or "/tests" in path:
            notes.append(f"modified test file: {path}")
        elif editable and not path.startswith(editable):
            notes.append(f"modified a file outside {', '.join(editable)}: {path}")
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


class _Scope:
    """One module, class or function body: its own nodes, and every value assigned to each name.

    A value of None marks a binding the gate can't see through (a parameter, a loop variable, an
    import), which is neither a fixed string nor one built at runtime.
    """

    def __init__(self, node: ast.AST, parent: _Scope | None = None):
        self.parent = parent
        self.values: dict[str, list[ast.AST | None]] = {}
        self.nodes: list[ast.AST] = []
        self.children: list[_Scope] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                if arg is not None:
                    self.values[arg.arg] = [None]
        stack = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.children.append(_Scope(child, self))
                continue
            self.nodes.append(child)
            self._record(child)
            stack.extend(ast.iter_child_nodes(child))

    def _bind(self, target: ast.AST, value: ast.AST | None) -> None:
        if isinstance(target, ast.Name):
            self.values.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind(element, None)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, None)

    def _record(self, node: ast.AST) -> None:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self._bind(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            self._bind(node.target, node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            self._bind(node.target, ast.BinOp(left=ast.Name(id=node.target.id), op=node.op, right=node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            self._bind(node.target, None)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            self._bind(node.optional_vars, None)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                self.values.setdefault((alias.asname or alias.name).split(".")[0], []).append(None)

    def owner(self, name: str) -> _Scope | None:
        scope = self
        while scope is not None and name not in scope.values:
            scope = scope.parent
        return scope


def _is_static_string(node: ast.AST | None, scope: _Scope, seen: frozenset = frozenset()) -> bool:
    """A string fully fixed in the source: literals, and + of literals or of names bound only to them."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return not any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_static_string(node.left, scope, seen) and _is_static_string(node.right, scope, seen)
    if isinstance(node, ast.Name):
        owner = scope.owner(node.id)
        if owner is None:
            return False
        if (id(owner), node.id) in seen:
            return True
        seen = seen | {(id(owner), node.id)}
        return all(_is_static_string(v, owner, seen) for v in owner.values[node.id])
    return False


def _is_dynamic_string(node: ast.AST | None, scope: _Scope, seen: frozenset = frozenset()) -> bool:
    """A string built at runtime, directly or through a variable assigned one."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return not (_is_static_string(node.left, scope) and _is_static_string(node.right, scope))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            return bool(node.args or node.keywords)
        if node.func.attr == "join":
            parts = node.args[0] if node.args else None
            fixed = isinstance(parts, (ast.List, ast.Tuple)) and all(_is_static_string(p, scope) for p in parts.elts)
            return not fixed
    if isinstance(node, ast.Name):
        owner = scope.owner(node.id)
        if owner is None or (id(owner), node.id) in seen:
            return False
        seen = seen | {(id(owner), node.id)}
        return any(_is_dynamic_string(v, owner, seen) for v in owner.values[node.id])
    return False


def find_unsafe_sql(source: str) -> list[int]:
    """Line numbers where a SQL sink receives a string built at runtime, inline or via a variable."""
    lines = []
    scopes = [_Scope(ast.parse(source))]
    while scopes:
        scope = scopes.pop()
        scopes.extend(scope.children)
        for node in scope.nodes:
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in SQL_SINKS and _is_dynamic_string(node.args[0], scope):
                lines.append(node.lineno)
    return sorted(lines)


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
    editable: tuple[str, ...] = (),
) -> RewardBreakdown:
    r = RewardBreakdown()
    r.format, notes = format_gate(changed_files, touched_paths, editable)
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
