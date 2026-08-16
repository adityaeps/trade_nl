"""Tests for the admin-triggered price sync runner.

The scraping itself is covered by running the script for real against the
competitor sites - what matters here is the bit the admin UI depends on:
progress counts, that one bad device doesn't abort the run, and that two
concurrent runs can't both scrape the catalog and race each other's
base_price writes.

`sync_device` and the database session are both faked, so no network and
no DB.
"""

import threading
import time
from uuid import uuid4

import pytest

from app.services import price_sync_runner
from app.services.price_sync_runner import SyncAlreadyRunningError, SyncRunState


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
    """Returns queued result sets in the order the runner queries them
    (active devices, then priced device ids when missing_only is set)."""

    def __init__(self, queued):
        self._queued = list(queued)
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec(self, _statement):
        return _FakeResult(self._queued.pop(0) if self._queued else [])

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _reset_state():
    """The runner keeps one module-level state (one API process, one run)."""
    price_sync_runner._state = SyncRunState()
    yield
    price_sync_runner._state = SyncRunState()


def _install(monkeypatch, devices, sync_device, priced_ids=None):
    queued = [devices] + ([[]] if priced_ids is None else [priced_ids])
    monkeypatch.setattr(price_sync_runner, "Session", lambda _engine: FakeSession(queued))
    monkeypatch.setattr(
        "scripts.sync_competitor_prices.sync_device", sync_device, raising=True
    )


def _wait_until_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = price_sync_runner.get_state()
        if state.status not in ("running",):
            return state
        time.sleep(0.01)
    raise AssertionError(f"sync did not finish within {timeout}s")


def test_counts_updated_and_unchanged_devices(monkeypatch):
    devices = [FakeDevice("iPhone 15"), FakeDevice("Galaxy S24"), FakeDevice("iPhone 13")]
    # Middle device finds no competitor price - §7 says leave its
    # base_price untouched, which sync_device signals by returning False.
    _install(monkeypatch, devices, lambda _s, _c, device: device.model != "Galaxy S24")

    price_sync_runner.start(missing_only=False, triggered_by="admin@example.com")
    state = _wait_until_done()

    assert state.status == "finished"
    assert (state.total_devices, state.processed, state.updated, state.failed) == (3, 3, 2, 1)
    assert state.failures == ["Galaxy S24 128GB: no competitor price found"]
    assert state.triggered_by == "admin@example.com"
    assert state.current_device is None


def test_one_raising_device_does_not_abort_the_run(monkeypatch):
    devices = [FakeDevice("iPhone 15"), FakeDevice("Galaxy S24"), FakeDevice("iPhone 13")]

    def sync_device(_session, _client, device):
        if device.model == "Galaxy S24":
            raise RuntimeError("connection reset")
        return True

    _install(monkeypatch, devices, sync_device)

    price_sync_runner.start(missing_only=False, triggered_by="admin@example.com")
    state = _wait_until_done()

    assert state.status == "finished"
    assert (state.processed, state.updated, state.failed) == (3, 2, 1)
    assert state.failures == ["Galaxy S24 128GB: RuntimeError: connection reset"]


def test_second_start_is_rejected_while_running(monkeypatch):
    release = threading.Event()
    _install(
        monkeypatch,
        [FakeDevice("iPhone 15")],
        lambda _s, _c, _d: release.wait(timeout=5) or True,
    )

    price_sync_runner.start(missing_only=False, triggered_by="admin@example.com")
    try:
        with pytest.raises(SyncAlreadyRunningError):
            price_sync_runner.start(missing_only=False, triggered_by="other@example.com")
    finally:
        release.set()

    assert _wait_until_done().status == "finished"


def test_missing_only_skips_devices_that_already_have_a_price(monkeypatch):
    priced = FakeDevice("iPhone 15")
    unpriced = FakeDevice("Galaxy S24")
    synced: list[str] = []

    class _BasePriceRow:
        device_id = priced.id

    _install(
        monkeypatch,
        [priced, unpriced],
        lambda _s, _c, device: bool(synced.append(device.model)) or True,
        priced_ids=[_BasePriceRow()],
    )

    price_sync_runner.start(missing_only=True, triggered_by="admin@example.com")
    state = _wait_until_done()

    assert synced == ["Galaxy S24"]
    assert (state.total_devices, state.updated) == (1, 1)
    assert state.missing_only is True


def test_run_failure_is_reported_not_swallowed(monkeypatch):
    def explode(_engine):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(price_sync_runner, "Session", explode)

    price_sync_runner.start(missing_only=False, triggered_by="admin@example.com")
    state = _wait_until_done()

    assert state.status == "failed"
    assert "database unreachable" in state.error
    assert state.finished_at is not None
