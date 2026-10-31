from conftest import me, patch, row


def test_get_own_profile(client):
    r = me(client, 1)
    assert r.status_code == 200
    assert r.json() == {"id": 1, "tenant_id": 1, "email": "rahim@acme.test", "display_name": "Rahim",
                        "timezone": "Asia/Dhaka", "role": "member", "credit_cents": 0}


def test_change_display_name(client):
    r = patch(client, 1, {"display_name": "Rahim U."})
    assert r.status_code == 200 and r.json()["display_name"] == "Rahim U."
    assert row(1)["display_name"] == "Rahim U."


def test_change_email(client):
    assert patch(client, 1, {"email": "rahim@acme.example"}).json()["email"] == "rahim@acme.example"


def test_user_header_required(client):
    assert client.get("/users/me").status_code == 422
