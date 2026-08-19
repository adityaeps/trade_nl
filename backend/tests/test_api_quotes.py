"""Integration tests for POST /quotes, GET /quotes/{id}, POST /quotes/{id}/confirm."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.device import Brand, DeviceCategory
from app.models.payout import Payout
from app.models.questionnaire import DeductionType, DisqualifyStatus, QuestionType
from app.models.quote import QuoteStatus
from sqlmodel import select
from tests.conftest import PYTEST_PREFIX
from tests.factories import (
    make_base_price,
    make_deduction_rule,
    make_device,
    make_question,
    make_question_set,
    make_quote,
    make_store,
)


def _phone_questionnaire(db_session, device):
    # category=tablet: real seed data already has phone/apple and
    # phone/samsung question sets, and the API's (category, brand) lookup
    # has no ordering guarantee among matches - a second phone/<brand> set
    # here could non-deterministically lose to the real one and pull in
    # unrelated deduction rules. tablet is unused for MVP (ARCHITECTURE.md
    # §3) so it's guaranteed to only match what this test creates. `device`
    # must be created with category=DeviceCategory.tablet to match.
    qs = make_question_set(db_session, category=DeviceCategory.tablet, brand=device.brand)
    q_condition = make_question(
        db_session,
        qs,
        type=QuestionType.single_select,
        options=[
            {"label": "Good", "value": "good"},
            {"label": "Cracked screen", "value": "cracked"},
        ],
    )
    q_simlock = make_question(
        db_session,
        qs,
        type=QuestionType.boolean,
        options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
    )
    q_water = make_question(
        db_session,
        qs,
        type=QuestionType.boolean,
        options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
    )
    make_deduction_rule(
        db_session, q_condition, "cracked", deduction_type=DeductionType.fixed, deduction_value="50.00"
    )
    make_deduction_rule(
        db_session,
        q_simlock,
        "yes",
        is_disqualifying=True,
        disqualify_status=DisqualifyStatus.rejected,
    )
    make_deduction_rule(
        db_session,
        q_water,
        "yes",
        is_disqualifying=True,
        disqualify_status=DisqualifyStatus.manual_review,
    )
    return q_condition, q_simlock, q_water


def test_create_quote_normal_price(client, db_session):
    device = make_device(db_session, brand=Brand.apple, category=DeviceCategory.tablet)
    make_base_price(db_session, device, base_price="500.00")
    q_condition, q_simlock, q_water = _phone_questionnaire(db_session, device)
    db_session.commit()

    resp = client.post(
        "/api/v1/quotes",
        json={
            "device_id": str(device.id),
            "answers": {
                str(q_condition.id): "cracked",
                str(q_simlock.id): "no",
                str(q_water.id): "no",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert Decimal(body["base_price_at_quote"]) == Decimal("500.00")
    assert Decimal(body["calculated_price"]) == Decimal("450.00")
    labels = {d["question_id"]: d["selected_label"] for d in body["answers_detail"]}
    assert labels[q_condition.id] == "Cracked screen"


def test_create_quote_disqualifying_rejected_path(client, db_session):
    device = make_device(db_session, brand=Brand.apple, category=DeviceCategory.tablet)
    make_base_price(db_session, device, base_price="500.00")
    q_condition, q_simlock, q_water = _phone_questionnaire(db_session, device)
    db_session.commit()

    resp = client.post(
        "/api/v1/quotes",
        json={
            "device_id": str(device.id),
            "answers": {
                str(q_condition.id): "good",
                str(q_simlock.id): "yes",
                str(q_water.id): "no",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["calculated_price"] is None


def test_create_quote_disqualifying_manual_review_path(client, db_session):
    device = make_device(db_session, brand=Brand.apple, category=DeviceCategory.tablet)
    make_base_price(db_session, device, base_price="500.00")
    q_condition, q_simlock, q_water = _phone_questionnaire(db_session, device)
    db_session.commit()

    resp = client.post(
        "/api/v1/quotes",
        json={
            "device_id": str(device.id),
            "answers": {
                str(q_condition.id): "good",
                str(q_simlock.id): "no",
                str(q_water.id): "yes",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "manual_review"
    assert body["calculated_price"] is None


def test_create_quote_404_unknown_device(client):
    resp = client.post(
        "/api/v1/quotes", json={"device_id": "00000000-0000-0000-0000-000000000000", "answers": {}}
    )
    assert resp.status_code == 404


def test_create_quote_409_no_base_price(client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = client.post("/api/v1/quotes", json={"device_id": str(device.id), "answers": {}})
    assert resp.status_code == 409


def test_get_quote_by_id(client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    db_session.commit()

    resp = client.get(f"/api/v1/quotes/{quote.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(quote.id)


def test_get_quote_404(client):
    resp = client.get("/api/v1/quotes/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_confirm_quote_creates_payout(client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, calculated_price=Decimal("425.00"))
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "courier",
            "customer_name": f"{PYTEST_PREFIX}Customer",
            "customer_email": "customer@example.com",
            "customer_phone": "+31612345678",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": f"{PYTEST_PREFIX}Customer",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["fulfillment_method"] == "courier"

    payout = db_session.exec(select(Payout).where(Payout.quote_id == quote.id)).first()
    assert payout is not None
    assert payout.amount == Decimal("425.00")
    assert payout.iban == "NL91ABNA0417164300"  # decrypted transparently on read


def test_confirm_quote_store_fulfillment_requires_store_id(client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "store",
            "customer_name": "x",
            "customer_email": "x@example.com",
            "customer_phone": "x",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": "x",
        },
    )
    assert resp.status_code == 422


def test_confirm_quote_unknown_store_id_404(client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "store",
            "store_id": 99999999,
            "customer_name": "x",
            "customer_email": "x@example.com",
            "customer_phone": "x",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": "x",
        },
    )
    assert resp.status_code == 404


def test_confirm_quote_with_valid_store(client, db_session):
    device = make_device(db_session)
    store = make_store(db_session)
    quote = make_quote(db_session, device)
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "store",
            "store_id": store.id,
            "customer_name": "x",
            "customer_email": "x@example.com",
            "customer_phone": "x",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": "x",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["store_id"] == store.id


def test_confirm_quote_409_when_not_pending(client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "courier",
            "customer_name": "x",
            "customer_email": "x@example.com",
            "customer_phone": "x",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": "x",
        },
    )
    assert resp.status_code == 409


def test_confirm_quote_409_when_expired(client, db_session):
    device = make_device(db_session)
    quote = make_quote(
        db_session, device, valid_until=datetime.now(timezone.utc) - timedelta(days=1)
    )
    db_session.commit()

    resp = client.post(
        f"/api/v1/quotes/{quote.id}/confirm",
        json={
            "fulfillment_method": "courier",
            "customer_name": "x",
            "customer_email": "x@example.com",
            "customer_phone": "x",
            "iban": "NL91ABNA0417164300",
            "account_holder_name": "x",
        },
    )
    assert resp.status_code == 409
    db_session.refresh(quote)
    assert quote.status == QuoteStatus.expired
