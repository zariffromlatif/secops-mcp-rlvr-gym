from verifier.gates import TOTAL_MAX, find_unsafe_sql, score

SAFE = '''
from sqlalchemy import text
def get(db, uid):
    return db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": uid})
'''

UNSAFE = '''
from sqlalchemy import text
def get(db, uid):
    return db.execute(text(f"SELECT * FROM users WHERE id = {uid}"))
'''


def test_static_check_flags_fstring_sql():
    assert find_unsafe_sql(UNSAFE) == [4]
    assert find_unsafe_sql(SAFE) == []


def test_static_check_follows_variables():
    via_variable = '''
def get(db, col):
    sql = f"SELECT * FROM users ORDER BY {col}"
    return db.execute(text(sql))
'''
    built_up = '''
def get(db, col, extra):
    sql = "SELECT * FROM users"
    sql += " ORDER BY " + col
    return db.execute(text(sql))
'''
    assert find_unsafe_sql(via_variable) == [4]
    assert find_unsafe_sql(built_up) == [5]


def test_static_check_flags_join_and_percent_formatting():
    assert find_unsafe_sql('db.execute(text(" ".join(["SELECT * FROM t ORDER BY", col])))') == [1]
    assert find_unsafe_sql('db.execute(text("SELECT * FROM t WHERE id = %s" % uid))') == [1]


def test_static_check_allows_strings_fixed_in_the_source():
    fixed = '''
BASE = "SELECT id FROM users"

def get(db, uid):
    sql = BASE + " WHERE id = :id"
    db.execute(text("SELECT " + "1"))
    db.execute(text(" ".join(["SELECT", "2"])))
    return db.execute(text(sql), {"id": uid})
'''
    assert find_unsafe_sql(fixed) == []


def test_edits_outside_editable_paths_fail_format():
    r = score({}, ["seed.sql"], {"app/db.py": SAFE}, regression=(10, 10), security=(5, 5), editable=("app/",))
    assert r.format < 0 and not r.solved
    assert r.notes == ["modified a file outside app/: seed.sql"]


def test_full_marks_for_clean_patch():
    r = score({"app/db.py": SAFE}, ["app/db.py"], {"app/db.py": SAFE}, regression=(10, 10), security=(5, 5))
    assert r.solved
    assert r.total == TOTAL_MAX
    assert r.normalized == 1.0


def test_editing_tests_short_circuits():
    r = score({"app/db.py": SAFE}, ["tests_public/test_db.py"], {"app/db.py": SAFE}, regression=(10, 10), security=(5, 5))
    assert r.total < 0
    assert r.regression == 0


def test_syntax_error_fails_format():
    r = score({"app/db.py": "def broken(:"}, ["app/db.py"], {}, regression=(0, 10), security=(0, 5))
    assert r.format < 0


def test_untouched_flaw_still_fails_static_gate():
    r = score({}, [], {"app/db.py": UNSAFE}, regression=(10, 10), security=(0, 5))
    assert r.static == 0
    assert not r.solved
