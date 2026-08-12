"""DEMO-ONLY seed data - NOT part of the real seed-data/ pipeline.

seed-data/devices.json carries no pricing figures (real competitor prices
are populated by the Sprint 7 sync process - ARCHITECTURE.md §7), and no
stores exist yet (store CRUD is Sprint 6). Without either, the catalog,
device detail, and confirm pages have nothing to display or select, so
Sprint 4's UI can't actually be exercised end to end yet.

This script fabricates illustrative base_prices (base_price, markup_pct,
liquidity_tier - all made up, NOT calibrated against real competitor data)
and a handful of demo stores, purely so the frontend has something to
render locally. `last_synced_at` is left null on every base_prices row to
honestly reflect that these were never produced by a real sync.

Do not run this against a staging/production database. Run once after
scripts/seed_db.py:

    python -m scripts.seed_demo_pricing
"""

from decimal import Decimal

from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Device
from app.models.pricing import BasePrice, LiquidityTier
from app.models.store import Store

# slug -> illustrative "up to €X" base price (EUR). Made up, not sourced
# from Swappie.nl/BuyBack.nl - see module docstring.
DEMO_PRICES: dict[str, str] = {
    "iphone-16-pro-max-256gb-black-titanium": "850.00",
    "iphone-16-pro-max-512gb-black-titanium": "950.00",
    "iphone-15-pro-128gb-natural-titanium": "650.00",
    "iphone-15-128gb-blue": "480.00",
    "iphone-14-128gb-midnight": "380.00",
    "iphone-13-128gb-starlight": "300.00",
    "iphone-se-3rd-gen-64gb-midnight": "180.00",
    "galaxy-s25-ultra-256gb-titanium-black": "750.00",
    "galaxy-s24-128gb-onyx-black": "420.00",
    "galaxy-a55-128gb-awesome-navy": "180.00",
    "galaxy-z-flip6-256gb-silver-shadow": "500.00",
}

DEMO_STORES = [
    {
        "name": "TradeIn Store Amsterdam Centrum",
        "address_line": "Damstraat 1",
        "city": "Amsterdam",
        "postal_code": "1012 JS",
        "lat": 52.3731,
        "lng": 4.8926,
        "opening_hours": {"mon_fri": "10:00-18:00", "sat": "10:00-17:00", "sun": "closed"},
    },
    {
        "name": "TradeIn Store Rotterdam Centraal",
        "address_line": "Coolsingel 100",
        "city": "Rotterdam",
        "postal_code": "3012 XJ",
        "lat": 51.9244,
        "lng": 4.4777,
        "opening_hours": {"mon_fri": "10:00-18:00", "sat": "10:00-17:00", "sun": "closed"},
    },
    {
        "name": "TradeIn Store Utrecht",
        "address_line": "Oudegracht 50",
        "city": "Utrecht",
        "postal_code": "3511 AS",
        "lat": 52.0907,
        "lng": 5.1214,
        "opening_hours": {"mon_fri": "10:00-18:00", "sat": "10:00-17:00", "sun": "closed"},
    },
]


def seed_prices(session: Session) -> None:
    created = 0
    for slug, price in DEMO_PRICES.items():
        device = session.exec(select(Device).where(Device.slug == slug)).first()
        if not device:
            print(f"  skip {slug}: device not found (seed_db.py run first?)")
            continue
        existing = session.exec(select(BasePrice).where(BasePrice.device_id == device.id)).first()
        if existing:
            continue
        session.add(
            BasePrice(
                device_id=device.id,
                base_price=Decimal(price),
                liquidity_tier=LiquidityTier.medium,
                # 0, not a placeholder markup: the business decided
                # (2026-08-08) to show raw competitor reference prices with
                # no markup for now, so customer-facing prices can be
                # verified 1:1 against BuyBack.nl. markup_pct stays in the
                # schema as an admin-configurable field (ARCHITECTURE.md
                # §11) - it just isn't applied by the pricing engine today.
                markup_pct=Decimal("0.00"),
                last_synced_at=None,
            )
        )
        created += 1
    session.commit()
    print(f"base_prices: {created} created, {len(DEMO_PRICES) - created} already present")


def seed_stores(session: Session) -> None:
    created = 0
    for s in DEMO_STORES:
        existing = session.exec(select(Store).where(Store.name == s["name"])).first()
        if existing:
            continue
        session.add(Store(**s, is_active=True))
        created += 1
    session.commit()
    print(f"stores: {created} created, {len(DEMO_STORES) - created} already present")


def main() -> None:
    with Session(engine) as session:
        seed_prices(session)
        seed_stores(session)


if __name__ == "__main__":
    main()
