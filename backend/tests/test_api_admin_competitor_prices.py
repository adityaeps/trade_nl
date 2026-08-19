"""Integration tests for /admin/competitor-prices (manual entry - ARCHITECTURE.md §7)."""

from decimal import Decimal

from app.models.pricing import BasePrice
from sqlmodel import select
from tests.factories import make_competitor_price, make_device


def test_upsert_creates_base_price_for_device_without_one(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "buyback", "price": "400.00"},
    )
    assert resp.status_code == 200, resp.text

    bp = db_session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
    assert bp is not None
    assert bp.base_price == Decimal("400.00")


def test_upsert_second_competitor_recomputes_average(admin_client, db_session):
    device = make_device(db_session)
    make_competitor_price(db_session, device, competitor_name="swappie", price="300.00")
    db_session.commit()

    resp = admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "buyback", "price": "320.00"},
    )
    assert resp.status_code == 200, resp.text

    bp = db_session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
    assert bp.base_price == Decimal("310.00")


def test_upsert_same_competitor_again_corrects_rather_than_duplicates(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "buyback", "price": "300.00"},
    )
    admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "buyback", "price": "350.00"},
    )

    bp = db_session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
    assert bp.base_price == Decimal("350.00")  # corrected, not averaged with the old value


def test_upsert_invalid_competitor_name_422(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "amazon", "price": "10.00"},
    )
    assert resp.status_code == 422


def test_upsert_non_positive_price_422(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={"device_id": str(device.id), "competitor_name": "buyback", "price": "0"},
    )
    assert resp.status_code == 422


def test_upsert_unknown_device_404(admin_client):
    resp = admin_client.put(
        "/api/v1/admin/competitor-prices",
        json={
            "device_id": "00000000-0000-0000-0000-000000000000",
            "competitor_name": "buyback",
            "price": "10.00",
        },
    )
    assert resp.status_code == 404


def test_list_with_stale_after_days_filter(admin_client, db_session):
    from datetime import datetime, timedelta, timezone

    device = make_device(db_session)
    fresh = make_competitor_price(db_session, device, competitor_name="buyback", price="100")
    stale = make_competitor_price(
        db_session,
        device,
        competitor_name="swappie",
        price="110",
        checked_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    db_session.commit()

    resp = admin_client.get(
        "/api/v1/admin/competitor-prices", params={"device_id": str(device.id), "stale_after_days": 7}
    )
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert stale.id in ids
    assert fresh.id not in ids


def test_delete_recomputes_average_from_remaining(admin_client, db_session):
    device = make_device(db_session)
    keep = make_competitor_price(db_session, device, competitor_name="buyback", price="300.00")
    remove = make_competitor_price(db_session, device, competitor_name="swappie", price="320.00")
    db_session.add(
        BasePrice(device_id=device.id, base_price=Decimal("310.00"), markup_pct=Decimal("0"),
                   liquidity_tier="medium")
    )
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/competitor-prices/{remove.id}")
    assert resp.status_code == 204

    bp = db_session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
    assert bp.base_price == Decimal("300.00")


def test_delete_last_price_leaves_base_price_untouched(admin_client, db_session):
    device = make_device(db_session)
    only = make_competitor_price(db_session, device, competitor_name="buyback", price="300.00")
    db_session.add(
        BasePrice(device_id=device.id, base_price=Decimal("300.00"), markup_pct=Decimal("0"),
                   liquidity_tier="medium")
    )
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/competitor-prices/{only.id}")
    assert resp.status_code == 204

    bp = db_session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
    assert bp.base_price == Decimal("300.00")  # untouched, not zeroed - §7


def test_delete_unknown_404(admin_client):
    resp = admin_client.delete("/api/v1/admin/competitor-prices/999999999")
    assert resp.status_code == 404
