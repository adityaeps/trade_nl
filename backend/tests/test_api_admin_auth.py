"""Integration tests for POST /admin/auth/login.

Only the login test itself uses a real, throwaway admin row created and
hashed exactly as scripts/create_admin.py would (hash_password + insert) -
every other admin-endpoint test in this suite bypasses auth entirely via
dependency_overrides per the task brief, so this is the one place JWT
issuance and bcrypt verification are actually exercised end to end.
"""

from app.core.security import decode_access_token
from tests.factories import make_admin_user


def test_login_success_issues_valid_token(client, db_session):
    admin, password = make_admin_user(db_session, password="Correct-Horse-1")
    db_session.commit()

    resp = client.post(
        "/api/v1/admin/auth/login", json={"email": admin.email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == admin.email
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == admin.email


def test_login_wrong_password_401(client, db_session):
    admin, _password = make_admin_user(db_session, password="Correct-Horse-1")
    db_session.commit()

    resp = client.post(
        "/api/v1/admin/auth/login", json={"email": admin.email, "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_inactive_user_401(client, db_session):
    admin, password = make_admin_user(db_session, password="Correct-Horse-1", is_active=False)
    db_session.commit()

    resp = client.post(
        "/api/v1/admin/auth/login", json={"email": admin.email, "password": password}
    )
    assert resp.status_code == 401


def test_login_unknown_email_401(client):
    resp = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "_pytest_no-such-admin@example.com", "password": "whatever"},
    )
    assert resp.status_code == 401


def test_me_endpoint_requires_auth(client):
    resp = client.get("/api/v1/admin/auth/me")
    assert resp.status_code == 401


def test_me_endpoint_with_valid_token(client, db_session):
    admin, password = make_admin_user(db_session, password="Correct-Horse-1", can_view_payouts=True)
    db_session.commit()

    login = client.post(
        "/api/v1/admin/auth/login", json={"email": admin.email, "password": password}
    )
    token = login.json()["access_token"]

    resp = client.get("/api/v1/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"email": admin.email, "can_view_payouts": True}
