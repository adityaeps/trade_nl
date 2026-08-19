"""Integration tests for /admin/quotes: listing, status-counts, and the
status-transition state machine (ALLOWED_TRANSITIONS in admin/quotes.py)."""

from decimal import Decimal

from app.models.payout import PayoutStatus
from app.models.quote import QuoteStatus
from sqlmodel import func, select
from app.models.quote import Quote
from tests.factories import make_device, make_payout, make_quote


def test_list_quotes_status_filter(admin_client, db_session):
    device = make_device(db_session)
    pending = make_quote(db_session, device, status=QuoteStatus.pending)
    confirmed = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/quotes", params={"status": "confirmed"})
    assert resp.status_code == 200
    ids = {q["id"] for q in resp.json()}
    assert str(confirmed.id) in ids
    assert str(pending.id) not in ids


def test_list_quotes_includes_device_label_and_payout_flag(admin_client, db_session):
    device = make_device(db_session, model="_pytest_LabelDevice", storage_gb=64)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    make_payout(db_session, quote)
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/quotes", params={"status": "confirmed", "limit": 500})
    row = next(r for r in resp.json() if r["id"] == str(quote.id))
    assert row["device_label"] == "_pytest_LabelDevice 64GB"
    assert row["has_payout"] is True


def test_status_counts_matches_manual_count(admin_client, db_session):
    device = make_device(db_session)
    make_quote(db_session, device, status=QuoteStatus.pending)
    make_quote(db_session, device, status=QuoteStatus.pending)
    make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/quotes/status-counts")
    assert resp.status_code == 200
    body = resp.json()

    manual_total = db_session.exec(select(func.count()).select_from(Quote)).one()
    manual_pending = db_session.exec(
        select(func.count()).select_from(Quote).where(Quote.status == QuoteStatus.pending)
    ).one()
    manual_confirmed = db_session.exec(
        select(func.count()).select_from(Quote).where(Quote.status == QuoteStatus.confirmed)
    ).one()

    assert body["total"] == manual_total
    assert body["by_status"]["pending"] == manual_pending
    assert body["by_status"]["confirmed"] == manual_confirmed


def test_status_transition_valid_confirmed_to_inspected(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/quotes/{quote.id}/status", json={"status": "inspected"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "inspected"


def test_status_transition_valid_manual_review_to_confirmed(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.manual_review, calculated_price=None)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/quotes/{quote.id}/status", json={"status": "confirmed"})
    assert resp.status_code == 200, resp.text


def test_status_transition_same_status_is_a_noop_success(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/quotes/{quote.id}/status", json={"status": "confirmed"})
    assert resp.status_code == 200


def test_status_transition_invalid_409(admin_client, db_session):
    device = make_device(db_session)
    # confirmed -> paid skips 'inspected', which is not an allowed transition.
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/quotes/{quote.id}/status", json={"status": "paid"})
    assert resp.status_code == 409


def test_status_transition_from_pending_is_never_allowed_409(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.pending)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/quotes/{quote.id}/status", json={"status": "inspected"})
    assert resp.status_code == 409


def test_status_update_adjusts_unpaid_payout_amount(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed, calculated_price=Decimal("400.00"))
    payout = make_payout(db_session, quote, amount=Decimal("400.00"), status=PayoutStatus.pending)
    db_session.commit()

    resp = admin_client.patch(
        f"/api/v1/admin/quotes/{quote.id}/status",
        json={"status": "inspected", "calculated_price": "350.00"},
    )
    assert resp.status_code == 200, resp.text

    db_session.refresh(payout)
    assert payout.amount == Decimal("350.00")


def test_status_update_does_not_touch_already_paid_payout(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.inspected, calculated_price=Decimal("400.00"))
    payout = make_payout(db_session, quote, amount=Decimal("400.00"), status=PayoutStatus.paid)
    db_session.commit()

    resp = admin_client.patch(
        f"/api/v1/admin/quotes/{quote.id}/status",
        json={"status": "paid", "calculated_price": "999.00"},
    )
    assert resp.status_code == 200, resp.text

    db_session.refresh(payout)
    assert payout.amount == Decimal("400.00")  # unchanged - already paid


def test_status_update_negative_price_422(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device, status=QuoteStatus.confirmed)
    db_session.commit()

    resp = admin_client.patch(
        f"/api/v1/admin/quotes/{quote.id}/status",
        json={"status": "inspected", "calculated_price": "-1.00"},
    )
    assert resp.status_code == 422


def test_status_update_404(admin_client):
    resp = admin_client.patch(
        "/api/v1/admin/quotes/00000000-0000-0000-0000-000000000000/status",
        json={"status": "inspected"},
    )
    assert resp.status_code == 404
