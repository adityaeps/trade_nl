from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.store import Store
from app.schemas.store import StoreOut

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
def list_stores(
    postal_code: str | None = None,
    limit: int = Query(5, le=50),
    session: Session = Depends(get_session),
):
    # TODO(assumption): postal_code -> lat/lng geocoding (Nominatim) and
    # haversine nearest-store sorting are Sprint 5 (ARCHITECTURE.md §10,
    # TASKS.md), not this sprint - postal_code is accepted here so the
    # frontend contract is stable, but isn't used to sort yet.
    stores = session.exec(
        select(Store).where(Store.is_active == True).order_by(Store.name)  # noqa: E712
    ).all()
    return stores[:limit]
