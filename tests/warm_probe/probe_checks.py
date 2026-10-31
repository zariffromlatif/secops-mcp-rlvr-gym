"""Hidden tests against tests/warm_probe/main.py (copied in as hidden/test_probe.py): every
escape attempt must have failed."""

import pytest


@pytest.fixture(scope="module")
def found(client):
    return client.get("/probe").json()


def test_owner_login_with_the_public_password_refused(found):
    assert found["owner_login"] is False


def test_no_ddl(found):
    assert found["ddl"] is False


def test_no_internet(found):
    assert found["internet"] is False


def test_host_files_not_reachable_through_symlinks(found):
    assert found["host_file"] is None


def test_tests_not_visible(found):
    assert set(found["work"]) <= {"READY", "app"} and found["episodes_dir"] is False


def test_fresh_container(found):
    assert found["marker_existed"] is False


def test_fresh_role(found):
    assert found["role_setting_before"] != "tainted"
