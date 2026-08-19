"""Shared fixtures for the API integration tests.

The local Postgres database backing these tests is real and already has
data from manual browser testing happening in parallel - see CLAUDE.md /
the task brief. `db_session` binds a Session to a single connection wrapped
in an outer transaction, with a SAVEPOINT restarted after every inner
commit (the standard SQLAlchemy "join a session to an external transaction"
pattern). That outer transaction is only ever rolled back, never committed,
so nothing a test - or an endpoint's own `session.commit()` - writes is
ever visible to another connection (including the app the manual testers
are poking at). Test rows are additionally named with a `_pytest_` prefix
as a second, purely-for-humans safety net in case anyone greps the DB.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session

from app.core.deps import get_current_admin
from app.db.session import engine, get_session
from app.main import app
from app.models.admin_user import AdminUser

PYTEST_PREFIX = "_pytest_"


@pytest.fixture()
def db_session():
    connection = engine.connect()
    outer_tx = connection.begin()
    session = Session(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_tx.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    """Plain, unauthenticated TestClient wired to the transactional session."""

    def _get_session_override():
        yield db_session

    app.dependency_overrides[get_session] = _get_session_override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


def _fake_admin(**overrides) -> AdminUser:
    defaults = dict(
        id=999_999,
        email=f"{PYTEST_PREFIX}admin@example.com",
        hashed_password="unused-bypassed-by-dependency-override",
        is_active=True,
        can_view_payouts=True,
    )
    defaults.update(overrides)
    return AdminUser(**defaults)


@pytest.fixture()
def admin_client(client):
    """Authenticated as a full-permission admin - bypasses JWT verification
    via dependency_overrides, per the task brief. Real login is covered
    separately in test_api_admin_auth.py."""
    admin = _fake_admin()
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


@pytest.fixture()
def admin_no_payouts_client(client):
    """Authenticated admin WITHOUT the payouts permission - for 403 tests.
    Still exercises the real can_view_payouts check in require_payouts_permission,
    only JWT verification itself is bypassed."""
    admin = _fake_admin(
        id=999_998,
        email=f"{PYTEST_PREFIX}admin-nopayouts@example.com",
        can_view_payouts=False,
    )
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
