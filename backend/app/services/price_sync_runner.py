"""Admin-triggered competitor price sync (ARCHITECTURE.md §7).

§7 runs the sync from a GitHub Actions cron so it doesn't depend on app
uptime. The deployed API sits on Render's free plan, which spins the
instance down when idle, so the business asked for the opposite trade:
no schedule at all, and a button in the admin UI that runs the sync on
demand while someone is actually watching.

This module owns that on-demand run. It reuses `sync_device()` from
`scripts/sync_competitor_prices.py` unchanged, so a button-triggered run
writes exactly what a command-line run writes - one scraping path, one
recompute path (§6/§7).

The run happens on a background thread rather than inside the request:
scraping is ~2-4s per device across the whole active catalog, far past
any sensible HTTP timeout. The frontend polls `GET /admin/price-sync`
for progress. State lives in process memory, which is enough here - the
API runs as a single Render instance (§3), and this is staff tooling, not
a customer path.

Two consequences of the free-plan spin-down worth knowing:

  * If the instance is suspended or restarted mid-run, the thread dies
    with it. `sync_device()` commits per device, so everything already
    synced is durable - re-running with `missing_only` picks up the rest.
  * Progress polling from the open admin tab is itself traffic, so the
    instance stays awake for the duration of a run someone is watching.

TODO(assumption): single-process, in-memory state. If the API is ever
scaled past one instance, "is a sync running?" needs to move to the
database (a `sync_runs` table) - ARCHITECTURE.md doesn't specify one.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Device
from app.models.pricing import BasePrice

logger = logging.getLogger(__name__)

# Cap on how many per-device failures we keep for the UI. A run over the
# whole catalog that fails everywhere (BuyBack.nl down, no network from
# the host) shouldn't grow an unbounded list in memory.
MAX_REPORTED_FAILURES = 50


class SyncAlreadyRunningError(RuntimeError):
    """Raised when a second run is requested while one is in flight."""


@dataclass(frozen=True)
class SyncRunState:
    """Snapshot of the current (or most recent) run.

    Frozen + copied out under the lock so a caller can never read a
    half-updated state while the worker thread is mutating it.
    """

    status: str = "idle"  # idle | running | finished | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    missing_only: bool = False
    triggered_by: str | None = None
    total_devices: int = 0
    processed: int = 0
    updated: int = 0
    failed: int = 0
    current_device: str | None = None
    failures: list[str] = field(default_factory=list)
    error: str | None = None


_lock = threading.Lock()
_state = SyncRunState()


def _device_label(device: Device) -> str:
    return f"{device.model} {device.storage_gb}GB"


def get_state() -> SyncRunState:
    with _lock:
        return _state


def _update(**changes) -> None:
    global _state
    with _lock:
        _state = replace(_state, **changes)


def start(*, missing_only: bool, triggered_by: str) -> SyncRunState:
    """Kicks off a background sync run.

    Raises SyncAlreadyRunningError if one is already in flight - two
    concurrent runs would scrape every device twice and race each other's
    base_price writes.
    """
    global _state
    with _lock:
        if _state.status == "running":
            raise SyncAlreadyRunningError("A price sync is already running")
        _state = SyncRunState(
            status="running",
            started_at=datetime.now(timezone.utc),
            missing_only=missing_only,
            triggered_by=triggered_by,
        )
        snapshot = _state

    thread = threading.Thread(
        target=_run,
        kwargs={"missing_only": missing_only},
        name="price-sync",
        daemon=True,  # never hold up an app shutdown/restart
    )
    thread.start()
    return snapshot


def _run(*, missing_only: bool) -> None:
    # Imported here, not at module import time: `scripts` is a sibling
    # package of `app` rather than part of it, so a deploy layout that
    # ships only `app/` should fail loudly on the one request that needs
    # the scraper instead of breaking app startup entirely.
    try:
        from scripts.sync_competitor_prices import _client, sync_device
    except ImportError as e:  # pragma: no cover - deploy-layout guard
        logger.exception("Price sync unavailable: scraper not importable")
        _update(
            status="failed",
            finished_at=datetime.now(timezone.utc),
            error=f"Sync script not available on this deployment: {e}",
        )
        return

    try:
        with Session(engine) as session, _client() as client:
            devices = list(
                session.exec(select(Device).where(Device.is_active == True)).all()  # noqa: E712
            )
            if missing_only:
                priced = {bp.device_id for bp in session.exec(select(BasePrice)).all()}
                devices = [d for d in devices if d.id not in priced]

            _update(total_devices=len(devices))
            logger.info(
                "Admin-triggered sync: %d devices%s",
                len(devices),
                " (missing-price only)" if missing_only else "",
            )

            for device in devices:
                label = _device_label(device)
                _update(current_device=label)
                state = get_state()
                try:
                    wrote = sync_device(session, client, device)
                except Exception as e:  # noqa: BLE001 - one device never kills the run
                    # sync_device already swallows the expected failures
                    # (timeouts, parse misses); anything reaching here is
                    # unexpected, so log the traceback and keep going.
                    logger.exception("Price sync failed for %s", label)
                    session.rollback()
                    wrote = False
                    reason = f"{label}: {type(e).__name__}: {e}"
                else:
                    reason = f"{label}: no competitor price found"

                if wrote:
                    _update(processed=state.processed + 1, updated=state.updated + 1)
                else:
                    failures = state.failures
                    if len(failures) < MAX_REPORTED_FAILURES:
                        failures = [*failures, reason]
                    _update(
                        processed=state.processed + 1,
                        failed=state.failed + 1,
                        failures=failures,
                    )

        _update(
            status="finished",
            finished_at=datetime.now(timezone.utc),
            current_device=None,
        )
        logger.info("Admin-triggered sync finished: %s", get_state())
    except Exception as e:  # noqa: BLE001 - the thread must never die silently
        logger.exception("Price sync run aborted")
        _update(
            status="failed",
            finished_at=datetime.now(timezone.utc),
            current_device=None,
            error=f"{type(e).__name__}: {e}",
        )
