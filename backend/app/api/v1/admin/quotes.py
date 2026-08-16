from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.deps import get_current_admin
from app.db.session import get_session
from app.models.admin_user import AdminUser
from app.models.device import Device
from app.models.payout import Payout
from app.models.quote import Quote, QuoteStatus
from app.models.store import Store

router = APIRouter(prefix="/quotes", tags=["admin:quotes"])


class AdminQuoteOut(BaseModel):
    id: UUID
    status: str
    device_label: str
    base_price_at_quote: Decimal
    calculated_price: Decimal | None
    fulfillment_method: str | None
    store_name: str | None
    customer_name: str | None
    customer_email: str | None
    customer_phone: str | None
    valid_until: datetime
    created_at: datetime
    has_payout: bool


class QuoteStatusUpdate(BaseModel):
    status: QuoteStatus
    # §8 allows adjusting the price when marking a quote inspected - the
    # physical device may not match what the customer reported.
    calculated_price: Decimal | None = None


def _to_out(session: Session, quote: Quote) -> AdminQuoteOut:
    device = session.get(Device, quote.device_id)
    store = session.get(Store, quote.store_id) if quote.store_id else None
    payout = session.exec(select(Payout).where(Payout.quote_id == quote.id)).first()
    return AdminQuoteOut(
        id=quote.id,
        status=quote.status,
        device_label=(
            f"{device.model} {device.storage_gb}GB" if device else "(device removed)"
        ),
        base_price_at_quote=quote.base_price_at_quote,
        calculated_price=quote.calculated_price,
        fulfillment_method=quote.fulfillment_method,
        store_name=store.name if store else None,
        customer_name=quote.customer_name,
        customer_email=quote.customer_email,
        customer_phone=quote.customer_phone,
        valid_until=quote.valid_until,
        created_at=quote.created_at,
        has_payout=payout is not None,
    )


@router.get("", response_model=list[AdminQuoteOut])
def list_quotes(
    status: QuoteStatus | None = None,
    limit: int = Query(100, le=500),
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    query = select(Quote)
    if status:
        query = query.where(Quote.status == status)
    quotes = session.exec(query.order_by(Quote.created_at.desc()).limit(limit)).all()
    return [_to_out(session, q) for q in quotes]


@router.get("/status-counts")
def status_counts(
    session: Session = Depends(get_session), _: AdminUser = Depends(get_current_admin)
):
    """Counts per status, so the orders screen can show filter badges
    without pulling every quote."""
    quotes = session.exec(select(Quote)).all()
    counts = {s.value: 0 for s in QuoteStatus}
    for q in quotes:
        counts[q.status.value if hasattr(q.status, "value") else q.status] += 1
    return {"total": len(quotes), "by_status": counts}


# Which status transitions staff may make by hand. Deliberately restrictive:
# `pending` and the two disqualification outcomes are set by the pricing
# engine (§6), and `confirmed` is set by the customer confirming - letting
# an admin set those by hand would let the UI contradict what the customer
# actually did.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    QuoteStatus.confirmed.value: {QuoteStatus.inspected.value, QuoteStatus.rejected.value},
    QuoteStatus.inspected.value: {QuoteStatus.paid.value, QuoteStatus.rejected.value},
    QuoteStatus.manual_review.value: {
        QuoteStatus.confirmed.value,
        QuoteStatus.rejected.value,
    },
}


@router.patch("/{quote_id}/status", response_model=AdminQuoteOut)
def update_quote_status(
    quote_id: UUID,
    payload: QuoteStatusUpdate,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    current = quote.status.value if hasattr(quote.status, "value") else quote.status
    target = payload.status.value
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target != current and target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot move a quote from '{current}' to '{target}'. "
                f"Allowed from '{current}': {', '.join(sorted(allowed)) or 'none'}."
            ),
        )

    if payload.calculated_price is not None:
        if payload.calculated_price < 0:
            raise HTTPException(status_code=422, detail="calculated_price cannot be negative")
        quote.calculated_price = payload.calculated_price
        # Keep the payout in step - it was created at confirm time from the
        # original figure, and paying out a superseded amount is the kind of
        # bug that only surfaces as a bank transfer for the wrong number.
        payout = session.exec(select(Payout).where(Payout.quote_id == quote.id)).first()
        if payout and payout.status.value != "paid":
            payout.amount = payload.calculated_price
            session.add(payout)

    quote.status = payload.status
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _to_out(session, quote)
