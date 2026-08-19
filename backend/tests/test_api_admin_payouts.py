"""Integration tests for /admin/payouts: permission gating, listing, mark-paid, CSV export."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models.payout import PayoutStatus
from tests.factories import make_device, make_payout, make_quote


def test_list_payouts_requires_auth(client):
    resp = client.get("/api/v1/admin/payouts")
    assert resp.status_code == 401


def test_list_payouts_requires_payouts_permission_403(admin_no_payouts_client):
    resp = admin_no_payouts_client.get("/api/v1/admin/payouts")
    assert resp.status_code == 403


def test_list_payouts_success_with_permission(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(
        db_session, device, customer_name="_pytest_Cust", customer_email="cust@example.com"
    )
    payout = make_payout(db_session, quote, iban="NL91ABNA0417164300", amount=Decimal("300.00"))
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/payouts", params={"limit": 500})
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == payout.id)
    assert row["iban"] == "NL91ABNA0417164300"  # decrypted for a permitted admin
    assert row["customer_name"] == "_pytest_Cust"
    assert Decimal(row["amount"]) == Decimal("300.00")


def test_list_payouts_status_filter(admin_client, db_session):
    device = make_device(db_session)
    q1 = make_quote(db_session, device)
    q2 = make_quote(db_session, device)
    pending = make_payout(db_session, q1, status=PayoutStatus.pending)
    paid = make_payout(
        db_session, q2, status=PayoutStatus.paid, paid_at=datetime.now(timezone.utc)
    )
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/payouts", params={"status": "paid", "limit": 500})
    ids = {r["id"] for r in resp.json()}
    assert paid.id in ids
    assert pending.id not in ids


def test_mark_paid_sets_status_and_timestamp(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    payout = make_payout(db_session, quote, status=PayoutStatus.pending)
    db_session.commit()

    resp = admin_client.patch(f"/api/v1/admin/payouts/{payout.id}", json={"status": "paid"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paid"
    assert body["paid_at"] is not None


def test_mark_paid_twice_is_idempotent_and_preserves_original_timestamp(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    payout = make_payout(db_session, quote, status=PayoutStatus.pending)
    db_session.commit()

    first = admin_client.patch(f"/api/v1/admin/payouts/{payout.id}", json={"status": "paid"})
    first_paid_at = first.json()["paid_at"]

    second = admin_client.patch(f"/api/v1/admin/payouts/{payout.id}", json={"status": "paid"})
    assert second.status_code == 200
    assert second.json()["paid_at"] == first_paid_at


def test_mark_paid_404(admin_client):
    resp = admin_client.patch("/api/v1/admin/payouts/999999999", json={"status": "paid"})
    assert resp.status_code == 404


def test_export_csv_headers_and_content(admin_client, db_session):
    device = make_device(db_session)
    quote = make_quote(db_session, device)
    payout = make_payout(
        db_session,
        quote,
        status=PayoutStatus.pending,
        amount=Decimal("123.45"),
        account_holder_name="_pytest_CSV Holder",
    )
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/payouts/export.csv", params={"status": "pending"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    body = resp.text
    assert "payout_id,quote_id,account_holder_name,iban,amount_eur,created_at" in body
    assert "_pytest_CSV Holder" in body
    assert "123.45" in body


def test_export_csv_requires_payouts_permission_403(admin_no_payouts_client):
    resp = admin_no_payouts_client.get("/api/v1/admin/payouts/export.csv")
    assert resp.status_code == 403
