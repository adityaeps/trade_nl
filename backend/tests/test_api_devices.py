"""Integration tests for GET /devices and GET /devices/{slug}.

The real catalog has 233 devices already in the DB, so every list test
scopes with `search=PYTEST_PREFIX` to only see rows this test created -
otherwise pagination/order assertions would be at the mercy of whatever's
actually in the catalog today.
"""

from decimal import Decimal

from app.models.device import Brand, DeviceCategory
from app.models.questionnaire import QuestionType
from tests.conftest import PYTEST_PREFIX
from tests.factories import make_base_price, make_device, make_question, make_question_set


def test_list_devices_pagination_and_order(client, db_session):
    # release_year descending is the documented sort - newest first.
    d_old = make_device(db_session, model=f"{PYTEST_PREFIX}Old", release_year=2018)
    d_new = make_device(db_session, model=f"{PYTEST_PREFIX}New", release_year=2024)
    d_mid = make_device(db_session, model=f"{PYTEST_PREFIX}Mid", release_year=2021)
    db_session.commit()

    page1 = client.get("/api/v1/devices", params={"search": PYTEST_PREFIX, "limit": 2, "offset": 0})
    page2 = client.get("/api/v1/devices", params={"search": PYTEST_PREFIX, "limit": 2, "offset": 2})
    assert page1.status_code == 200 and page2.status_code == 200

    ids_in_order = [row["id"] for row in page1.json()] + [row["id"] for row in page2.json()]
    assert ids_in_order == [str(d_new.id), str(d_mid.id), str(d_old.id)]
    assert len(page1.json()) == 2
    assert len(page2.json()) == 1


def test_list_devices_brand_filter(client, db_session):
    apple = make_device(db_session, brand=Brand.apple, model=f"{PYTEST_PREFIX}AppleOne")
    samsung = make_device(db_session, brand=Brand.samsung, model=f"{PYTEST_PREFIX}SamsungOne")
    db_session.commit()

    resp = client.get("/api/v1/devices", params={"search": PYTEST_PREFIX, "brand": "samsung"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(samsung.id) in ids
    assert str(apple.id) not in ids


def test_list_devices_search_filter(client, db_session):
    match = make_device(db_session, model=f"{PYTEST_PREFIX}FindMeXYZ")
    other = make_device(db_session, model=f"{PYTEST_PREFIX}Unrelated")
    db_session.commit()

    resp = client.get("/api/v1/devices", params={"search": "FindMeXYZ"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(match.id) in ids
    assert str(other.id) not in ids


def test_list_devices_price_up_to_null_vs_populated(client, db_session):
    priced = make_device(db_session, model=f"{PYTEST_PREFIX}Priced")
    make_base_price(db_session, priced, base_price="499.99")
    unpriced = make_device(db_session, model=f"{PYTEST_PREFIX}Unpriced")
    db_session.commit()

    resp = client.get("/api/v1/devices", params={"search": PYTEST_PREFIX})
    by_id = {row["id"]: row for row in resp.json()}

    assert Decimal(by_id[str(priced.id)]["price_up_to"]) == Decimal("499.99")
    assert by_id[str(unpriced.id)]["price_up_to"] is None


def test_list_devices_excludes_inactive(client, db_session):
    active = make_device(db_session, model=f"{PYTEST_PREFIX}Active", is_active=True)
    inactive = make_device(db_session, model=f"{PYTEST_PREFIX}Inactive", is_active=False)
    db_session.commit()

    resp = client.get("/api/v1/devices", params={"search": PYTEST_PREFIX})
    ids = {row["id"] for row in resp.json()}
    assert str(active.id) in ids
    assert str(inactive.id) not in ids


def test_get_device_detail_includes_storage_variants_and_gated_questions(client, db_session):
    # category=tablet, not phone: the real seed data already has phone/apple
    # and phone/samsung question sets, and the endpoint's
    # (category, brand) lookup has no ordering guarantee among matches, so a
    # second phone/apple set created here could non-deterministically lose
    # to the real one. tablet is unused for MVP (ARCHITECTURE.md §3), so
    # it's guaranteed to only match the set this test creates.
    device = make_device(
        db_session,
        brand=Brand.apple,
        category=DeviceCategory.tablet,
        model=f"{PYTEST_PREFIX}Variant Phone",
        color="Blue",
        storage_gb=128,
        has_s_pen=False,
    )
    sibling = make_device(
        db_session,
        brand=Brand.apple,
        category=DeviceCategory.tablet,
        model=f"{PYTEST_PREFIX}Variant Phone",
        color="Blue",
        storage_gb=256,
    )
    make_base_price(db_session, device, base_price="600.00")
    make_base_price(db_session, sibling, base_price="700.00")

    qs = make_question_set(db_session, category=DeviceCategory.tablet, brand=Brand.apple)
    q_root = make_question(
        db_session,
        qs,
        text=f"{PYTEST_PREFIX}Does everything work?",
        type=QuestionType.boolean,
        display_order=1,
        options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
    )
    q_branch = make_question(
        db_session,
        qs,
        text=f"{PYTEST_PREFIX}What doesn't work?",
        type=QuestionType.multi_select,
        display_order=2,
        options=[{"label": "Screen", "value": "screen"}],
        depends_on_question_id=q_root.id,
        depends_on_value="no",
    )
    # Gated by a device attribute this device doesn't have - must not appear.
    q_gated = make_question(
        db_session,
        qs,
        text=f"{PYTEST_PREFIX}S-Pen condition?",
        type=QuestionType.boolean,
        display_order=3,
        requires_device_attribute="has_s_pen",
    )
    db_session.commit()

    resp = client.get(f"/api/v1/devices/{device.slug}")
    assert resp.status_code == 200
    body = resp.json()

    assert {v["id"] for v in body["storage_variants"]} == {str(device.id), str(sibling.id)}

    question_ids = {q["id"] for q in body["questions"]}
    assert q_root.id in question_ids
    assert q_branch.id in question_ids  # depends_on questions are NOT filtered here - §6
    assert q_gated.id not in question_ids  # device-attribute gating filters this out


def test_get_device_404_for_unknown_slug(client):
    resp = client.get(f"/api/v1/devices/{PYTEST_PREFIX}does-not-exist")
    assert resp.status_code == 404
