from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.store import Store
from app.schemas.store import StoreOut
from app.services.geocoding import (
    geocode_postal_code,
    normalize_postal_code,
    sort_stores_by_distance,
)

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
def list_stores(
    postal_code: str | None = None,
    limit: int = Query(5, le=50),
    session: Session = Depends(get_session),
):
    """Nearest active stores (§8).

    With a postal code, results are sorted by haversine distance from it and
    each carries `distance_km`. Without one - or if the code can't be
    geocoded - the full list comes back name-ordered with `distance_km`
    null, so a bad postcode degrades the picker rather than emptying it.
    """
    stores = session.exec(
        select(Store).where(Store.is_active == True).order_by(Store.name)  # noqa: E712
    ).all()

    origin = None
    if postal_code:
        origin = geocode_postal_code(normalize_postal_code(postal_code))

    ranked = sort_stores_by_distance(stores, origin)[:limit]
    return [
        StoreOut(
            **store.model_dump(),
            distance_km=round(distance, 1) if distance is not None else None,
        )
        for store, distance in ranked
    ]
