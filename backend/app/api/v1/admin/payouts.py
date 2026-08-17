import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.deps import require_payouts_permission
from app.db.session import get_session
from app.models.admin_user import AdminUser
from app.models.payout import Payout, PayoutStatus
from app.models.quote import Quote

router = APIRouter(prefix="/payouts", tags=["admin:payouts"])


class PayoutOut(BaseModel):
    id: int
    quote_id: str
    account_holder_name: str
    iban: str
    amount: Decimal
    status: str
    paid_at: datetime | None
    created_at: datetime
    customer_name: str | None
    customer_email: str | None


class MarkPaidRequest(BaseModel):
    status: PayoutStatus = PayoutStatus.paid


def _to_out(payout: Payout, quote: Quote | None) -> PayoutOut:
    return PayoutOut(
        id=payout.id,
        quote_id=str(payout.quote_id),
        account_holder_name=payout.account_holder_name,
        # Decrypted by the EncryptedString column type on read (§5). This
        # endpoint is behind require_payouts_permission precisely because
        # it exposes plaintext IBANs.
        iban=payout.iban,
        amount=payout.amount,
        status=payout.status,
        paid_at=payout.paid_at,
        created_at=payout.created_at,
        customer_name=quote.customer_name if quote else None,
        customer_email=quote.customer_email if quote else None,
    )


@router.get("", response_model=list[PayoutOut])
def list_payouts(
    status: PayoutStatus | None = None,
    limit: int = Query(200, le=1000),
    session: Session = Depends(get_session),
    _: AdminUser = Depends(require_payouts_permission),
):
    query = select(Payout)
    if status:
        query = query.where(Payout.status == status)
    payouts = session.exec(query.order_by(Payout.created_at.desc()).limit(limit)).all()
    if not payouts:
        return []

    # One bulk lookup instead of one Quote query per payout.
    quote_ids = {p.quote_id for p in payouts}
    quotes = {q.id: q for q in session.exec(select(Quote).where(Quote.id.in_(quote_ids))).all()}
    return [_to_out(p, quotes.get(p.quote_id)) for p in payouts]


@router.get("/export.csv")
def export_csv(
    status: PayoutStatus = PayoutStatus.pending,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(require_payouts_permission),
):
    """CSV of the payout queue for bank bulk upload (§8).

    Deliberately a neutral columns-and-values export rather than a specific
    bank's SEPA format: which bank, and therefore which layout (or whether
    they want pain.001 XML instead), is a business decision that hasn't been
    made. Reshaping columns later is trivial; guessing at a format now would
    bake in an assumption that silently produces rejected transfers.

    Amounts use a plain dot decimal and no thousands separator, which every
    importer accepts.
    """
    payouts = session.exec(
        select(Payout).where(Payout.status == status).order_by(Payout.created_at)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["payout_id", "quote_id", "account_holder_name", "iban", "amount_eur", "created_at"]
    )
    for p in payouts:
        writer.writerow(
            [
                p.id,
                str(p.quote_id),
                p.account_holder_name,
                p.iban,
                f"{p.amount:.2f}",
                p.created_at.isoformat(),
            ]
        )

    buffer.seek(0)
    filename = f"payouts-{status.value}-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{payout_id}", response_model=PayoutOut)
def mark_paid(
    payout_id: int,
    payload: MarkPaidRequest,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(require_payouts_permission),
):
    payout = session.get(Payout, payout_id)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    current = payout.status.value if hasattr(payout.status, "value") else payout.status
    quote = session.get(Quote, payout.quote_id)
    if current == PayoutStatus.paid.value and payload.status == PayoutStatus.paid:
        # Not an error, but don't silently rewrite paid_at - the original
        # timestamp is the audit trail for a transfer that already happened.
        return _to_out(payout, quote)

    payout.status = payload.status
    payout.paid_at = (
        datetime.now(timezone.utc) if payload.status == PayoutStatus.paid else None
    )
    session.add(payout)
    session.commit()
    session.refresh(payout)
    return _to_out(payout, quote)
