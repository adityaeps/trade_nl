from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    response: Response,
    brand: Brand | None = None,
    search: str | None = None,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """One page of the catalog, newest models first.

    Paged because the catalog is a few hundred devices and the storefront
    loads it as the customer scrolls - returning all of them made the first
    paint wait on every row plus its price.

    Ordered by `release_year` descending (see services/release_year.py) with
    unknown years last, then model and storage so the sequence is stable
    between pages - an unstable ORDER BY makes offset paging drop or repeat
    rows.
    """
    # Public, non-personalized catalog data - safe for the browser to reuse
    # for a short window instead of re-fetching on every render/navigation.
    # 30s is short enough that a price-sync run (admin-triggered, not
    # scheduled - see §7) is never stale for long; stale-while-revalidate
    # lets the browser show the cached page instantly while it quietly
    # refetches, rather than blocking on a fresh request every time.
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"

    query = select(Device, BasePrice.base_price).where(Device.is_active == True)  # noqa: E712
    # Outer join, not a lookup per device: this endpoint used to run one
    # extra query for every row returned (N+1), which is most of what made
    # a full catalog load slow. Devices with no base_price still appear,
    # with price_up_to null ("price coming soon").
    query = query.join(BasePrice, BasePrice.device_id == Device.id, isouter=True)
    if brand:
        query = query.where(Device.brand == brand)
    if search:
        query = query.where(Device.model.ilike(f"%{search}%"))

    query = query.order_by(
        Device.release_year.desc().nullslast(),
        Device.model,
        Device.storage_gb,
    )
    rows = session.exec(query.offset(offset).limit(limit)).all()
    return [_to_summary(device, price) for device, price in rows]


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
