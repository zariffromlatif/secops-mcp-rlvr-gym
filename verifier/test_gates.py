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
