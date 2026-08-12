from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.device import Brand, Device
from app.models.pricing import BasePrice
from app.models.questionnaire import DeductionRule, Question, QuestionSet
from app.schemas.device import DeviceDetail, DeviceSummary, QuestionOut
from app.services.pricing_engine import filter_questions_for_device

router = APIRouter(prefix="/devices", tags=["devices"])


def _price_for(session: Session, device_id) -> Decimal | None:
    row = session.exec(select(BasePrice).where(BasePrice.device_id == device_id)).first()
    return row.base_price if row else None


def _to_summary(device: Device, price: Decimal | None) -> DeviceSummary:
    return DeviceSummary(
        id=device.id,
        brand=device.brand,
        model=device.model,
        storage_gb=device.storage_gb,
        color=device.color,
        slug=device.slug,
        image_url=device.image_url,
        has_s_pen=device.has_s_pen,
        price_up_to=price,
    )


@router.get("", response_model=list[DeviceSummary])
def list_devices(
    brand: Brand | None = None,
    search: str | None = None,
    session: Session = Depends(get_session),
):
    query = select(Device).where(Device.is_active == True)  # noqa: E712
    if brand:
        query = query.where(Device.brand == brand)
    if search:
        query = query.where(Device.model.ilike(f"%{search}%"))
    devices = session.exec(query.order_by(Device.brand, Device.model, Device.storage_gb)).all()
    return [_to_summary(d, _price_for(session, d.id)) for d in devices]


@router.get("/{slug}", response_model=DeviceDetail)
def get_device(slug: str, session: Session = Depends(get_session)):
    device = session.exec(select(Device).where(Device.slug == slug)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    siblings = session.exec(
        select(Device)
        .where(
            Device.brand == device.brand,
            Device.model == device.model,
            Device.color == device.color,
        )
        .order_by(Device.storage_gb)
    ).all()

    questions: list[Question] = []
    question_set = session.exec(
        select(QuestionSet).where(
            QuestionSet.category == device.category, QuestionSet.brand == device.brand
        )
    ).first()
    if question_set:
        all_questions = session.exec(
            select(Question)
            .where(Question.question_set_id == question_set.id)
            .order_by(Question.display_order)
        ).all()
        questions = filter_questions_for_device(all_questions, device)

    question_out_list = []
    for q in questions:
        rules = session.exec(
            select(DeductionRule).where(DeductionRule.question_id == q.id)
        ).all()
        question_out_list.append(
            QuestionOut(
                id=q.id,
                text=q.text,
                type=q.type,
                display_order=q.display_order,
                options=q.options,
                depends_on_question_id=q.depends_on_question_id,
                depends_on_value=q.depends_on_value,
                requires_device_attribute=q.requires_device_attribute,
                deduction_rules=rules,
            )
        )

    return DeviceDetail(
        **_to_summary(device, _price_for(session, device.id)).model_dump(),
        storage_variants=[_to_summary(s, _price_for(session, s.id)) for s in siblings],
        questions=question_out_list,
    )
