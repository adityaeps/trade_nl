from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.device import Device
from app.models.payout import Payout
from app.models.pricing import BasePrice
from app.models.questionnaire import DeductionRule, Question, QuestionSet
from app.models.quote import FulfillmentMethod, Quote, QuoteStatus
from app.models.store import Store
from app.schemas.quote import (
    AnsweredQuestionOut,
    QuoteConfirmRequest,
    QuoteCreateRequest,
    QuoteOut,
)
from app.services.pricing_engine import calculate_quote_price, find_disqualification

router = APIRouter(prefix="/quotes", tags=["quotes"])

QUOTE_VALIDITY_DAYS = 7


def _deduction_rules_for(session: Session, device: Device) -> list[DeductionRule]:
    question_set = session.exec(
        select(QuestionSet).where(
            QuestionSet.category == device.category, QuestionSet.brand == device.brand
        )
    ).first()
    if not question_set:
        return []
    question_ids = session.exec(
        select(Question.id).where(Question.question_set_id == question_set.id)
    ).all()
    if not question_ids:
        return []
    return session.exec(
        select(DeductionRule).where(DeductionRule.question_id.in_(question_ids))
    ).all()


def _build_answers_detail(session: Session, quote: Quote) -> list[AnsweredQuestionOut]:
    if not quote.answers:
        return []
    question_ids = [int(qid) for qid in quote.answers.keys()]
    questions = session.exec(select(Question).where(Question.id.in_(question_ids))).all()
    questions_by_id = {q.id: q for q in questions}

    detail = []
    for qid_str, value in quote.answers.items():
        question = questions_by_id.get(int(qid_str))
        if not question:
            continue
        label = next(
            (opt["label"] for opt in question.options if opt["value"] == value), value
        )
        detail.append(
            AnsweredQuestionOut(
                question_id=question.id,
                question_text=question.text,
                selected_value=value,
                selected_label=label,
            )
        )
    detail.sort(key=lambda d: questions_by_id[d.question_id].display_order)
    return detail


def _to_quote_out(session: Session, quote: Quote) -> QuoteOut:
    return QuoteOut(
        id=quote.id,
        device_id=quote.device_id,
        answers=quote.answers,
        answers_detail=_build_answers_detail(session, quote),
        status=quote.status,
        base_price_at_quote=quote.base_price_at_quote,
        calculated_price=quote.calculated_price,
        fulfillment_method=quote.fulfillment_method,
        store_id=quote.store_id,
        customer_name=quote.customer_name,
        customer_email=quote.customer_email,
        customer_phone=quote.customer_phone,
        valid_until=quote.valid_until,
    )


@router.post("", response_model=QuoteOut)
def create_quote(payload: QuoteCreateRequest, session: Session = Depends(get_session)):
    device = session.get(Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    base_price_row = session.exec(
        select(BasePrice).where(BasePrice.device_id == device.id)
    ).first()
    if not base_price_row:
        raise HTTPException(status_code=409, detail="No price available for this device yet")

    rules = _deduction_rules_for(session, device)
    disqualify_status = find_disqualification(payload.answers, rules)

    quote = Quote(
        device_id=device.id,
        answers=payload.answers,
        base_price_at_quote=base_price_row.base_price,
        valid_until=datetime.now(timezone.utc) + timedelta(days=QUOTE_VALIDITY_DAYS),
    )
    if disqualify_status:
        # DisqualifyStatus and QuoteStatus are separate enums that share the
        # 'rejected'/'manual_review' string values by design (§6) - convert
        # by value rather than assigning the wrong enum type directly.
        quote.status = QuoteStatus(disqualify_status.value)
        quote.calculated_price = None
    else:
        quote.calculated_price = calculate_quote_price(
            base_price_row.base_price, payload.answers, rules
        )
        quote.status = QuoteStatus.pending

    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _to_quote_out(session, quote)


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: UUID, session: Session = Depends(get_session)):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _to_quote_out(session, quote)


@router.post("/{quote_id}/confirm", response_model=QuoteOut)
def confirm_quote(
    quote_id: UUID, payload: QuoteConfirmRequest, session: Session = Depends(get_session)
):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.pending:
        raise HTTPException(
            status_code=409, detail=f"Quote cannot be confirmed from status '{quote.status}'"
        )
    if quote.valid_until < datetime.now(timezone.utc):
        quote.status = QuoteStatus.expired
        session.add(quote)
        session.commit()
        raise HTTPException(status_code=409, detail="Quote has expired")

    if payload.fulfillment_method == FulfillmentMethod.store and not payload.store_id:
        raise HTTPException(status_code=422, detail="store_id is required for store fulfillment")
    if payload.store_id is not None and not session.get(Store, payload.store_id):
        raise HTTPException(status_code=404, detail="Store not found")

    quote.fulfillment_method = payload.fulfillment_method
    quote.store_id = payload.store_id
    quote.customer_name = payload.customer_name
    quote.customer_email = payload.customer_email
    quote.customer_phone = payload.customer_phone
    quote.status = QuoteStatus.confirmed
    session.add(quote)

    session.add(
        Payout(
            quote_id=quote.id,
            iban=payload.iban,
            account_holder_name=payload.account_holder_name,
            amount=quote.calculated_price or Decimal(0),
        )
    )
    session.commit()
    session.refresh(quote)
    return _to_quote_out(session, quote)
