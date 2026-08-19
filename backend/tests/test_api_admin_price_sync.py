"""Integration tests for GET/POST /admin/price-sync.

Faking `price_sync_runner.Session` and `scripts.sync_competitor_prices.sync_device`,
the same way tests/test_price_sync_runner.py already does for the unit-level
tests of the runner itself - this avoids both live network calls to
BuyBack.nl/Swappie and any real DB writes via the runner's own engine-bound
session (which is separate from the transactional `db_session` fixture used
elsewhere in this suite, since the runner opens its own connection).
"""

import threading
import time
from uuid import uuid4

import pytest

from app.services import price_sync_runner


class FakeDevice:
    def __init__(self, model: str, storage_gb: int = 128):
        self.id = uuid4()
        self.model = model
        self.storage_gb = storage_gb


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, queued):
        self._queued = list(queued)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec(self, _statement):
        return _FakeResult(self._queued.pop(0) if self._queued else [])

    def rollback(self):
        pass


def _install(monkeypatch, devices, sync_device):
    queued = [devices, []]
    monkeypatch.setattr(price_sync_runner, "Session", lambda _engine: FakeSession(queued))
    monkeypatch.setattr(
        "scripts.sync_competitor_prices.sync_device", sync_device, raising=True
    )


def _wait_until_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = price_sync_runner.get_state()
        if state.status != "running":
            return state
        time.sleep(0.01)
    raise AssertionError(f"sync did not finish within {timeout}s")


@pytest.fixture(autouse=True)
def _reset_runner_state():
    price_sync_runner._state = price_sync_runner.SyncRunState()
    yield
    price_sync_runner._state = price_sync_runner.SyncRunState()


def test_get_status_idle_before_any_run(admin_client):
    resp = admin_client.get("/api/v1/admin/price-sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_requires_auth(client):
    assert client.get("/api/v1/admin/price-sync").status_code == 401
    assert client.post("/api/v1/admin/price-sync").status_code == 401


def test_start_runs_to_completion_and_status_reflects_it(admin_client, monkeypatch):
    devices = [FakeDevice("iPhone 15"), FakeDevice("Galaxy S24")]
    _install(monkeypatch, devices, lambda _s, _c, device: device.model != "Galaxy S24")

    start_resp = admin_client.post("/api/v1/admin/price-sync", json={"missing_only": False})
    assert start_resp.status_code == 202, start_resp.text
    assert start_resp.json()["status"] == "running"

    _wait_until_done()

    status_resp = admin_client.get("/api/v1/admin/price-sync")
    body = status_resp.json()
    assert body["status"] == "finished"
    assert (body["total_devices"], body["processed"], body["updated"], body["failed"]) == (2, 2, 1, 1)
    assert body["triggered_by"] == "_pytest_admin@example.com"


def test_second_start_while_running_returns_409(admin_client, monkeypatch):
    release = threading.Event()
    _install(
        monkeypatch, [FakeDevice("iPhone 15")], lambda _s, _c, _d: release.wait(timeout=5) or True
    )

    first = admin_client.post("/api/v1/admin/price-sync")
    assert first.status_code == 202
    try:
        second = admin_client.post("/api/v1/admin/price-sync")
        assert second.status_code == 409
    finally:
        release.set()
        _wait_until_done()
