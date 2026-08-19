"""Row builders for the API integration tests. Not a test file itself.

Every human-visible identifier (slug, model, email, store name) carries
tests.conftest.PYTEST_PREFIX so a leaked row would be obvious in a manual
DB browse - the real safety net is the rolled-back transaction in
conftest.db_session, this is belt-and-braces.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel import Session

from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.models.device import Brand, Device, DeviceCategory
from app.models.payout import Payout, PayoutStatus
from app.models.pricing import BasePrice, CompetitorPrice, LiquidityTier
from app.models.questionnaire import (
    DeductionRule,
    DeductionType,
    DisqualifyStatus,
    Question,
    QuestionSet,
    QuestionType,
)
from app.models.quote import FulfillmentMethod, Quote, QuoteStatus
from app.models.store import Store
from tests.conftest import PYTEST_PREFIX


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def make_device(session: Session, **overrides) -> Device:
    n = _uid()
    defaults = dict(
        brand=Brand.apple,
        model=f"{PYTEST_PREFIX}iPhone {n}",
        storage_gb=128,
        color="Black",
        category=DeviceCategory.phone,
        has_s_pen=False,
        slug=f"{PYTEST_PREFIX}iphone-{n}",
        is_active=True,
    )
    defaults.update(overrides)
    device = Device(**defaults)
    session.add(device)
    session.flush()
    return device


def make_base_price(
    session: Session,
    device: Device,
    base_price="500.00",
    markup_pct="3.00",
    liquidity_tier=LiquidityTier.medium,
    **overrides,
) -> BasePrice:
    bp = BasePrice(
        device_id=device.id,
        base_price=Decimal(base_price),
        markup_pct=Decimal(markup_pct),
        liquidity_tier=liquidity_tier,
        **overrides,
    )
    session.add(bp)
    session.flush()
    return bp


def make_competitor_price(session: Session, device: Device, competitor_name="buyback", price="500.00", **overrides) -> CompetitorPrice:
    cp = CompetitorPrice(
        device_id=device.id,
        competitor_name=competitor_name,
        price=Decimal(price),
        condition_tier="good",
        source_url="https://example.com",
        **overrides,
    )
    session.add(cp)
    session.flush()
    return cp


def make_question_set(session: Session, category=DeviceCategory.phone, brand=Brand.apple, name=None) -> QuestionSet:
    qs = QuestionSet(category=category, brand=brand, name=name or f"{PYTEST_PREFIX}question set {_uid()}")
    session.add(qs)
    session.flush()
    return qs


def make_question(
    session: Session,
    question_set: QuestionSet,
    text=None,
    type=QuestionType.single_select,
    display_order=1,
    options=None,
    **overrides,
) -> Question:
    q = Question(
        question_set_id=question_set.id,
        text=text or f"{PYTEST_PREFIX}question {_uid()}",
        type=type,
        display_order=display_order,
        options=options if options is not None else [],
        **overrides,
    )
    session.add(q)
    session.flush()
    return q


def make_deduction_rule(
    session: Session,
    question: Question,
    option_value: str,
    deduction_type=DeductionType.fixed,
    deduction_value="10.00",
    is_disqualifying=False,
    disqualify_status: DisqualifyStatus | None = None,
) -> DeductionRule:
    rule = DeductionRule(
        question_id=question.id,
        option_value=option_value,
        deduction_type=deduction_type,
        deduction_value=Decimal(deduction_value),
        is_disqualifying=is_disqualifying,
        disqualify_status=disqualify_status,
    )
    session.add(rule)
    session.flush()
    return rule


def make_store(session: Session, **overrides) -> Store:
    n = _uid()
    defaults = dict(
        name=f"{PYTEST_PREFIX}Store {n}",
        address_line="Teststraat 1",
        city="Amsterdam",
        postal_code="1012 JS",
        lat=52.3731,
        lng=4.8926,
        opening_hours={},
        is_active=True,
    )
    defaults.update(overrides)
    store = Store(**defaults)
    session.add(store)
    session.flush()
    return store


def make_quote(session: Session, device: Device, **overrides) -> Quote:
    defaults = dict(
        device_id=device.id,
        answers={},
        base_price_at_quote=Decimal("500.00"),
        calculated_price=Decimal("450.00"),
        status=QuoteStatus.pending,
        valid_until=datetime.now(timezone.utc) + timedelta(days=7),
    )
    defaults.update(overrides)
    quote = Quote(**defaults)
    session.add(quote)
    session.flush()
    return quote


def make_payout(session: Session, quote: Quote, **overrides) -> Payout:
    defaults = dict(
        quote_id=quote.id,
        iban="NL91ABNA0417164300",
        account_holder_name=f"{PYTEST_PREFIX}Holder",
        amount=quote.calculated_price or Decimal("0"),
        status=PayoutStatus.pending,
    )
    defaults.update(overrides)
    payout = Payout(**defaults)
    session.add(payout)
    session.flush()
    return payout


def make_admin_user(session: Session, password="Sup3rSecret!!", **overrides) -> tuple[AdminUser, str]:
    n = _uid()
    defaults = dict(
        email=f"{PYTEST_PREFIX}user-{n}@example.com",
        hashed_password=hash_password(password),
        is_active=True,
        can_view_payouts=False,
    )
    defaults.update(overrides)
    admin = AdminUser(**defaults)
    session.add(admin)
    session.flush()
    return admin, password
