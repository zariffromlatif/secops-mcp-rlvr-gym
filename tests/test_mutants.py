"""Mutant generation, fixed-line parsing and the survivor review list. No database needed."""

import mutants

SOURCE = '''from sqlalchemy import text

def fee(db, days, total):
    if days <= 0 or total < 1:
        return 0
    rows = db.execute(text("SELECT x FROM t WHERE a = :a AND b >= :b ORDER BY x DESC"))
    return min(total, days * 2)
'''


def test_mutants_cover_python_and_sql_and_keep_formatting():
    found = {(m.kind, m.before, m.after) for m in mutants.mutants_for(SOURCE, {4})}
    assert ("comparison", "<=", "<") in found
    assert ("boolean", "or", "and") in found
    assert ("name", "min", "max") in found
    assert ("sql: drop condition", "AND b >= :b", "") in found
    assert ("sql: comparison", ">=", ">") in found
    assert ("sql: order", "DESC", "ASC") in found
    for m in mutants.mutants_for(SOURCE, {4}):
        assert m.source != SOURCE and m.source.count("\n") == SOURCE.count("\n")
        assert m.in_fix == (m.line == 4)


def test_fix_lines_are_the_added_lines_of_the_patched_file(tmp_path):
    patch = tmp_path / "gold.patch"
    patch.write_text("--- a/app/main.py\n+++ b/app/main.py\n@@ -1,3 +1,4 @@\n a\n-b\n+B\n+C\n d\n")
    assert mutants.fix_lines(patch) == {2, 3}


def test_unreviewed_survivors_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(mutants, "OUT", tmp_path)
    monkeypatch.setattr(mutants, "REVIEWED", [tmp_path / "equivalent.yaml"])
    (tmp_path / "equivalent.yaml").write_text("t L1 < -> <=: harmless\n")
    survivors = [{"line": 1, "kind": "comparison", "before": "<", "after": "<=", "in_fix": True},
                 {"line": 2, "kind": "constant", "before": "5", "after": "6", "in_fix": True}]
    rows = [{"task": "t", "mutants": 3, "killed": 1, "fix_mutants": 3, "fix_killed": 1, "survivors": survivors}]
    assert mutants.write_report(rows) == ["t L2 5 -> 6"]
    report = (tmp_path / "README.md").read_text()
    assert "harmless" in report and "**UNREVIEWED**" in report
