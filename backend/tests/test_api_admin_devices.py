"""Integration tests for /admin/devices and /admin/devices/{id}/base-price."""

from decimal import Decimal

from app.models.device import Brand
from app.models.pricing import LiquidityTier
from sqlmodel import select
from app.models.device import Device
from tests.conftest import PYTEST_PREFIX
from tests.factories import make_base_price, make_device


def test_list_devices_requires_auth(client):
    resp = client.get("/api/v1/admin/devices")
    assert resp.status_code == 401


def test_list_devices_returns_correct_base_price_per_device(admin_client, db_session):
    """Guards the N+1 fix in admin/devices.py: the outer-join list must
    attach the right BasePrice to the right Device, not just any price."""
    priced = make_device(db_session, model=f"{PYTEST_PREFIX}Priced")
    make_base_price(db_session, priced, base_price="321.50", markup_pct="5.00", liquidity_tier=LiquidityTier.high)
    unpriced = make_device(db_session, model=f"{PYTEST_PREFIX}Unpriced")
    other = make_device(db_session, model=f"{PYTEST_PREFIX}Other")
    make_base_price(db_session, other, base_price="999.00")
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/devices", params={"search": PYTEST_PREFIX})
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}

    assert Decimal(by_id[str(priced.id)]["base_price"]) == Decimal("321.50")
    assert by_id[str(priced.id)]["liquidity_tier"] == "high"
    assert by_id[str(unpriced.id)]["base_price"] is None
    assert Decimal(by_id[str(other.id)]["base_price"]) == Decimal("999.00")


def test_list_devices_brand_and_search_filters(admin_client, db_session):
    apple = make_device(db_session, brand=Brand.apple, model=f"{PYTEST_PREFIX}AppleAdmin")
    samsung = make_device(db_session, brand=Brand.samsung, model=f"{PYTEST_PREFIX}SamsungAdmin")
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/devices", params={"brand": "apple", "search": PYTEST_PREFIX})
    ids = {row["id"] for row in resp.json()}
    assert str(apple.id) in ids
    assert str(samsung.id) not in ids


def test_list_devices_include_inactive_toggle(admin_client, db_session):
    active = make_device(db_session, model=f"{PYTEST_PREFIX}ActiveAdmin", is_active=True)
    inactive = make_device(db_session, model=f"{PYTEST_PREFIX}InactiveAdmin", is_active=False)
    db_session.commit()

    resp = admin_client.get(
        "/api/v1/admin/devices", params={"search": PYTEST_PREFIX, "include_inactive": False}
    )
    ids = {row["id"] for row in resp.json()}
    assert str(active.id) in ids
    assert str(inactive.id) not in ids

    resp = admin_client.get(
        "/api/v1/admin/devices", params={"search": PYTEST_PREFIX, "include_inactive": True}
    )
    ids = {row["id"] for row in resp.json()}
    assert str(inactive.id) in ids


def test_create_device(admin_client):
    payload = {
        "brand": "apple",
        "model": f"{PYTEST_PREFIX}Created iPhone",
        "storage_gb": 256,
        "slug": f"{PYTEST_PREFIX}created-iphone",
    }
    resp = admin_client.post("/api/v1/admin/devices", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == payload["slug"]
    assert body["is_active"] is True


def test_create_device_duplicate_slug_409(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = admin_client.post(
        "/api/v1/admin/devices",
        json={"brand": "apple", "model": "x", "storage_gb": 64, "slug": device.slug},
    )
    assert resp.status_code == 409


def test_update_device_partial(admin_client, db_session):
    device = make_device(db_session, model=f"{PYTEST_PREFIX}Original", color="Black")
    db_session.commit()

    resp = admin_client.put(f"/api/v1/admin/devices/{device.id}", json={"color": "Silver"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["color"] == "Silver"
    assert body["model"] == f"{PYTEST_PREFIX}Original"  # untouched


def test_update_device_404(admin_client):
    resp = admin_client.put(
        "/api/v1/admin/devices/00000000-0000-0000-0000-000000000000", json={"color": "Red"}
    )
    assert resp.status_code == 404


def test_deactivate_device_is_soft_delete(admin_client, db_session):
    device = make_device(db_session, is_active=True)
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/devices/{device.id}")
    assert resp.status_code == 204

    # Not hard-deleted - still present in the DB, just deactivated.
    row = db_session.exec(select(Device).where(Device.id == device.id)).first()
    assert row is not None
    assert row.is_active is False


def test_upsert_base_price_creates_then_updates(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    payload = {"base_price": "100.00", "markup_pct": "2.00", "liquidity_tier": "low"}
    created = admin_client.put(f"/api/v1/admin/devices/{device.id}/base-price", json=payload)
    assert created.status_code == 200, created.text
    assert Decimal(created.json()["base_price"]) == Decimal("100.00")

    updated_payload = {"base_price": "150.00", "markup_pct": "4.00", "liquidity_tier": "high"}
    updated = admin_client.put(f"/api/v1/admin/devices/{device.id}/base-price", json=updated_payload)
    assert updated.status_code == 200, updated.text
    assert Decimal(updated.json()["base_price"]) == Decimal("150.00")
    assert updated.json()["liquidity_tier"] == "high"


def test_upsert_base_price_negative_422(admin_client, db_session):
    device = make_device(db_session)
    db_session.commit()

    resp = admin_client.put(
        f"/api/v1/admin/devices/{device.id}/base-price",
        json={"base_price": "-1.00", "markup_pct": "0", "liquidity_tier": "medium"},
    )
    assert resp.status_code == 422
