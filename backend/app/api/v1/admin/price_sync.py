"""Manual competitor price sync trigger - see ARCHITECTURE.md §7.

There is no schedule any more: the API idles down on Render's free plan,
so instead of a nightly cron the sync is started by hand from the admin
Pricing page. Two endpoints, both admin-only:

    POST /admin/price-sync   start a run (409 if one is already going)
    GET  /admin/price-sync   progress of the current/most recent run

The actual work happens on a background thread - see
app/services/price_sync_runner.py for why, and for what happens if the
instance sleeps mid-run.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_admin
from app.models.admin_user import AdminUser
from app.services import price_sync_runner
from app.services.price_sync_runner import SyncAlreadyRunningError, SyncRunState

router = APIRouter(prefix="/price-sync", tags=["admin:price-sync"])


class PriceSyncStart(BaseModel):
    missing_only: bool = False


class PriceSyncStatus(BaseModel):
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    missing_only: bool
    triggered_by: str | None
    total_devices: int
    processed: int
    updated: int
    failed: int
    current_device: str | None
    failures: list[str]
    error: str | None


def _to_status(state: SyncRunState) -> PriceSyncStatus:
    return PriceSyncStatus(**vars(state))


@router.get("", response_model=PriceSyncStatus)
def price_sync_status(_: AdminUser = Depends(get_current_admin)):
    """Progress of the run in flight, or the result of the last one.

    Returns status="idle" if this process has never run a sync - including
    after a restart, which wipes the in-memory history (not the synced
    prices themselves, which are committed per device).
    """
    return _to_status(price_sync_runner.get_state())


@router.post("", response_model=PriceSyncStatus, status_code=status.HTTP_202_ACCEPTED)
def start_price_sync(
    payload: PriceSyncStart | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Starts a competitor price sync and returns immediately.

    202, not 200: the run is accepted, not finished - poll GET for
    progress. `missing_only` re-scrapes just the devices that still have
    no base price, which is the cheap path for filling gaps after a
    partial run (§7: never re-crawl the whole catalog for a handful of
    stragglers).
    """
    options = payload or PriceSyncStart()
    try:
        state = price_sync_runner.start(
            missing_only=options.missing_only, triggered_by=admin.email
        )
    except SyncAlreadyRunningError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return _to_status(state)
