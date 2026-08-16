"""Manual competitor price entry - the §7 "first version" path.

ARCHITECTURE.md §7 specifies the sync starting as a manual admin form that
staff fill in weekly, automating only once the manual process is proven.
The scraper was built first at the business's request, so this endpoint now
serves two purposes rather than one:

  * entering prices for models the scraper can't reach (Swappie is behind
    Cloudflare; a handful of BuyBack models fail transiently), and
  * correcting a scraped figure without waiting for the next nightly run.

Writes go through the same path as the scraper: upsert `competitor_prices`,
append to `price_history`, then recompute `base_prices.base_price` with
`calculate_reference_price`. Keeping one recompute path means a manually
entered price and a scraped one are averaged identically (§6).
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from app.core.deps import get_current_admin
from app.db.session import get_session
from app.models.admin_user import AdminUser
from app.models.device import Device
from app.models.pricing import BasePrice, CompetitorPrice, LiquidityTier, PriceHistory
from app.services.pricing_engine import calculate_reference_price

router = APIRouter(prefix="/competitor-prices", tags=["admin:competitor-prices"])

# The two competitors ARCHITECTURE.md §1 names. Free text would let typos
# ("Buyback", "buy back") silently create parallel rows that never overwrite
# each other and quietly skew the average.
KNOWN_COMPETITORS = {"buyback", "swappie"}


class CompetitorPriceOut(BaseModel):
    id: int
    device_id: UUID
    device_label: str
    competitor_name: str
    price: Decimal
    condition_tier: str
    source_url: str
    checked_at: datetime
    age_days: int


class CompetitorPriceIn(BaseModel):
    device_id: UUID
    competitor_name: str
    price: Decimal
    condition_tier: str = "manual entry (best condition)"
    source_url: str = ""

    @field_validator("competitor_name")
    @classmethod
    def _known_competitor(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in KNOWN_COMPETITORS:
            raise ValueError(
                f"competitor_name must be one of: {', '.join(sorted(KNOWN_COMPETITORS))}"
            )
        return normalized

    @field_validator("price")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        # A 0 price is never a real competitor offer - it's how the scraper
        # signals a failed fetch, and letting one in would drag the average
        # down silently.
        if v <= 0:
            raise ValueError("price must be greater than 0")
        return v


def _to_out(session: Session, cp: CompetitorPrice) -> CompetitorPriceOut:
    device = session.get(Device, cp.device_id)
    checked = cp.checked_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return CompetitorPriceOut(
        id=cp.id,
        device_id=cp.device_id,
        device_label=(
            f"{device.model} {device.storage_gb}GB" if device else "(device removed)"
        ),
        competitor_name=cp.competitor_name,
        price=cp.price,
        condition_tier=cp.condition_tier,
        source_url=cp.source_url,
        checked_at=checked,
        age_days=(datetime.now(timezone.utc) - checked).days,
    )


@router.get("", response_model=list[CompetitorPriceOut])
def list_competitor_prices(
    device_id: UUID | None = None,
    stale_after_days: int | None = Query(
        None,
        description="Only return prices older than this many days (§8: filterable by staleness)",
    ),
    limit: int = Query(200, le=1000),
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    query = select(CompetitorPrice)
    if device_id:
        query = query.where(CompetitorPrice.device_id == device_id)
    rows = session.exec(query.order_by(CompetitorPrice.checked_at)).all()

    out = [_to_out(session, cp) for cp in rows]
    if stale_after_days is not None:
        out = [o for o in out if o.age_days >= stale_after_days]
    return out[:limit]


@router.put("", response_model=CompetitorPriceOut)
def upsert_competitor_price(
    payload: CompetitorPriceIn,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    """Records a manually-entered competitor price and recomputes base_price.

    Upserts on (device_id, competitor_name) so re-entering a price corrects
    the existing row rather than stacking duplicates that would each count
    toward the average.
    """
    device = session.get(Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    now = datetime.now(timezone.utc)
    existing = session.exec(
        select(CompetitorPrice).where(
            CompetitorPrice.device_id == payload.device_id,
            CompetitorPrice.competitor_name == payload.competitor_name,
        )
    ).first()

    if existing:
        existing.price = payload.price
        existing.condition_tier = payload.condition_tier
        existing.source_url = payload.source_url
        existing.checked_at = now
        session.add(existing)
        row = existing
    else:
        row = CompetitorPrice(
            device_id=payload.device_id,
            competitor_name=payload.competitor_name,
            price=payload.price,
            condition_tier=payload.condition_tier,
            source_url=payload.source_url,
            checked_at=now,
        )
        session.add(row)

    session.flush()  # so the new row counts toward the recompute below

    all_prices = session.exec(
        select(CompetitorPrice).where(CompetitorPrice.device_id == payload.device_id)
    ).all()
    reference_price = calculate_reference_price(all_prices)

    session.add(
        PriceHistory(device_id=device.id, base_price=reference_price, recorded_at=now)
    )

    base = session.exec(
        select(BasePrice).where(BasePrice.device_id == device.id)
    ).first()
    if base:
        base.base_price = reference_price
        base.last_synced_at = now
    else:
        base = BasePrice(
            device_id=device.id,
            base_price=reference_price,
            liquidity_tier=LiquidityTier.medium,
            # markup_pct stays 0 - the business runs raw reference prices
            # for now (see TASKS.md Sprint 2).
            markup_pct=Decimal("0"),
            last_synced_at=now,
        )
    session.add(base)

    session.commit()
    session.refresh(row)
    return _to_out(session, row)


@router.delete("/{price_id}", status_code=204)
def delete_competitor_price(
    price_id: int,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    """Removes a competitor price and recomputes base_price without it.

    If it was the only price for that device, base_price is left untouched
    rather than zeroed - §7's rule is to keep the last good value and let
    staleness surface in the UI, not to write a bad one.
    """
    row = session.get(CompetitorPrice, price_id)
    if not row:
        raise HTTPException(status_code=404, detail="Competitor price not found")

    device_id = row.device_id
    session.delete(row)
    session.flush()

    remaining = session.exec(
        select(CompetitorPrice).where(CompetitorPrice.device_id == device_id)
    ).all()
    if remaining:
        base = session.exec(
            select(BasePrice).where(BasePrice.device_id == device_id)
        ).first()
        if base:
            base.base_price = calculate_reference_price(remaining)
            session.add(base)

    session.commit()
