"""Imports the device catalog (models + storage variants) from BuyBack.nl.

Discovers every iPhone / Samsung Galaxy model BuyBack.nl lists, filters to
those released within MAX_AGE_YEARS, reads each model's storage options off
its first wizard question, and upserts one `devices` row per
(brand, model, storage).

Deliberately does NOT fetch prices or images - those are separate concerns
already handled by `sync_competitor_prices.py` and `fetch_device_images.py`.
Run this first, then those two:

    python -m scripts.import_catalog_from_buyback
    python -m scripts.sync_competitor_prices
    python -m scripts.fetch_device_images

Writes `seed-data/buyback_slugs.json` mapping our (brand, model) to
BuyBack.nl's URL slug, so the price/image scripts can find each model
without re-deriving a slug (their naming is irregular - see
BUYBACK_SLUG_OVERRIDES in sync_competitor_prices.py).

Rights note: same as fetch_device_images.py - model names and storage
options are factual catalog data, but see that script's docstring for the
image-copyright caveat.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Brand, Device, DeviceCategory
from scripts.sync_competitor_prices import storage_gb_from_label

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_catalog")

USER_AGENT = (
    "PhoneTradeInPlatformBot/1.0 "
    "(+https://github.com/<org>/phone-tradein-nl; catalog sync; contact: <business-email>)"
)
REQUEST_DELAY_SECONDS = 1.0
MAX_AGE_YEARS = 6
CURRENT_YEAR = datetime.now(timezone.utc).year
MIN_RELEASE_YEAR = CURRENT_YEAR - MAX_AGE_YEARS  # 2020 when run in 2026

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed-data"

# Release years by BuyBack.nl slug. Hardcoded rather than scraped because
# BuyBack.nl doesn't publish a release date, and "how old is this model" is
# the filter the business actually asked for. Sourced from public launch
# dates; verify if a borderline model matters commercially.
# TODO(assumption): models absent from this map are skipped with a warning
# rather than guessed at - add an entry when BuyBack.nl lists something new.
RELEASE_YEAR: dict[str, int] = {
    # --- iPhone ---
    "iphone-8": 2017, "iphone-8-plus": 2017, "iphone-x": 2017,
    "iphone-xr": 2018, "iphone-xs": 2018, "iphone-xs-max": 2018,
    "iphone-11": 2019, "iphone-11-pro": 2019, "iphone-11-pro-max": 2019,
    "iphone-se-2-2020": 2020,
    "iphone-12": 2020, "iphone-12-mini": 2020, "iphone-12-pro": 2020, "iphone-12-pro-max": 2020,
    "iphone-13": 2021, "iphone-13-mini": 2021, "iphone-13-pro": 2021, "iphone-13-pro-max": 2021,
    "iphone-se-3-2022": 2022,
    "iphone-14": 2022, "iphone-14-plus": 2022, "iphone-14-pro": 2022, "iphone-14-pro-max": 2022,
    "iphone-15": 2023, "iphone-15-plus": 2023, "iphone-15-pro": 2023, "iphone-15-pro-max": 2023,
    "iphone-16": 2024, "iphone-16-plus": 2024, "iphone-16-pro": 2024, "iphone-16-pro-max": 2024,
    "iphone-16e": 2025,
    "iphone-17": 2025, "iphone-17-pro": 2025, "iphone-17-pro-max": 2025, "iphone-17e": 2025,
    "iphone-air": 2025,
    # --- Samsung Galaxy S ---
    "samsung-galaxy-s7-edge": 2016,
    "samsung-galaxy-s8": 2017, "samsung-galaxy-s8-plus": 2017,
    "samsung-galaxy-s9": 2018, "samsung-galaxy-s9-plus": 2018,
    "samsung-galaxy-s10": 2019, "samsung-galaxy-s10-plus": 2019, "samsung-galaxy-s10e": 2019,
    "samsung-galaxy-s10-lite": 2020,
    "samsung-galaxy-s20": 2020, "samsung-galaxy-s20-plus": 2020,
    "samsung-galaxy-s20-ultra": 2020, "samsung-galaxy-s20-fe": 2020,
    "samsung-galaxy-s21": 2021, "samsung-galaxy-s21-plus": 2021,
    "samsung-galaxy-s21-ultra": 2021, "samsung-galaxy-s21-fe": 2022,
    "samsung-galaxy-s22": 2022, "samsung-galaxy-s22-plus": 2022, "samsung-galaxy-s22-ultra": 2022,
    "samsung-galaxy-s23": 2023, "samsung-galaxy-s23-plus": 2023,
    "samsung-galaxy-s23-ultra": 2023, "samsung-galaxy-s23-fe": 2023,
    "samsung-galaxy-s24": 2024, "samsung-galaxy-s24-plus": 2024,
    "samsung-galaxy-s24-ultra": 2024, "samsung-galaxy-s24-fe": 2024,
    "samsung-galaxy-s25": 2025, "samsung-galaxy-s25-plus-2": 2025,
    "samsung-galaxy-s25-ultra": 2025, "samsung-galaxy-s25-edge": 2025,
    "samsung-galaxy-s25-fe": 2025,
    "samsung-galaxy-s26": 2026, "samsung-galaxy-s26-plus": 2026, "samsung-galaxy-s26-ultra": 2026,
    # --- Samsung Galaxy Note ---
    "samsung-galaxy-note7": 2016, "samsung-galaxy-note8": 2017, "samsung-galaxy-note9": 2018,
    "samsung-galaxy-note10": 2019, "samsung-galaxy-note10-plus": 2019,
    "samsung-galaxy-note10-lite": 2020,
    "samsung-galaxy-note20": 2020, "samsung-galaxy-note20-ultra": 2020,
    # --- Samsung Galaxy Z ---
    "samsung-galaxy-z-fold": 2019,
    "samsung-galaxy-z-flip": 2020, "samsung-galaxy-z-fold-2": 2020,
    "samsung-galaxy-z-flip3": 2021, "samsung-galaxy-z-fold-3": 2021,
    "samsung-galaxy-z-flip-4": 2022, "samsung-galaxy-z-fold-4": 2022,
    "samsung-galaxy-z-flip-5": 2023, "samsung-galaxy-z-fold-5": 2023,
    "samsung-galaxy-z-flip-6": 2024, "samsung-galaxy-z-fold-6": 2024,
    "samsung-galaxy-z-flip7": 2025, "samsung-galaxy-z-flip7-fe": 2025,
    "samsung-galaxy-z-fold7": 2025,
    # --- Samsung Galaxy A ---
    "samsung-galaxy-a3-2016": 2016, "samsung-galaxy-a5-2016": 2016,
    "samsung-galaxy-a3-2017": 2017, "samsung-galaxy-a5-2017": 2017,
    "samsung-galaxy-a6-2018": 2018, "samsung-galaxy-a6-plus-2018": 2018,
    "samsung-galaxy-a7-2018": 2018, "samsung-galaxy-a9-2018": 2018,
    "samsung-galaxy-a10": 2019, "samsung-galaxy-a20e": 2019, "samsung-galaxy-a20s": 2019,
    "samsung-galaxy-a40": 2019, "samsung-galaxy-a50": 2019, "samsung-galaxy-a51": 2019,
    "samsung-galaxy-a70": 2019, "samsung-galaxy-a71": 2019, "samsung-galaxy-a80": 2019,
    "samsung-galaxy-a11": 2020, "samsung-galaxy-a12": 2020, "samsung-galaxy-a21s": 2020,
    "samsung-galaxy-a41": 2020, "samsung-galaxy-a42": 2020,
    "samsung-galaxy-a22s": 2021, "samsung-galaxy-a52": 2021,
    "samsung-galaxy-a52s": 2021, "samsung-galaxy-a72": 2021,
    "samsung-galaxy-a13": 2022, "samsung-galaxy-a23": 2022,
    "samsung-galaxy-a33": 2022, "samsung-galaxy-a53": 2022,
    "samsung-galaxy-a14": 2023, "samsung-galaxy-a34": 2023, "samsung-galaxy-a54": 2023,
    "samsung-galaxy-a15": 2024, "samsung-galaxy-a25": 2024,
    "samsung-galaxy-a35": 2024, "samsung-galaxy-a55": 2024,
}

# S-Pen support. ARCHITECTURE.md §11 / questions.json flag "which Samsung
# models get has_s_pen = true" as an open business/catalog decision; this
# applies the industry-standard answer (Note line, S-series Ultra from the
# S21 Ultra onward, and Z Fold from Fold 3 onward) as a documented default.
# Surface for confirmation rather than treating as settled.
S_PEN_PATTERNS = (
    re.compile(r"^samsung-galaxy-note"),
    re.compile(r"^samsung-galaxy-s(2[1-9]|[3-9]\d)-ultra"),
    re.compile(r"^samsung-galaxy-z-fold-?([3-9]|\d\d)"),
)

_OPTION_RE = re.compile(
    r'data-field-id="(?P<field_id>\d+)"\s+data-option-id="(?P<option_id>\d+)"[^>]*>\s*'
    r"<span>\s*(?P<label>[^<]+?)\s*</span>",
    re.IGNORECASE,
)
_H1_RE = re.compile(r"<h1[^>]*>\s*(.*?)\s*</h1>", re.IGNORECASE | re.DOTALL)
# Most models label storage plainly ("128GB", "1TB"), but many mid-range
# Samsungs label it "<storage>/<RAM>" ("128GB/4GB", "256GB/12GB"). Only the
# leading storage figure maps to devices.storage_gb; RAM isn't modelled.


def discover_slugs(client: httpx.Client) -> dict[Brand, list[str]]:
    out: dict[Brand, list[str]] = {}
    for brand, cat in ((Brand.apple, "iphone"), (Brand.samsung, "samsung-galaxy")):
        found: set[str] = set()
        for page in range(1, 10):
            url = (
                f"https://buyback.nl/telefoon/{cat}"
                if page == 1
                else f"https://buyback.nl/telefoon/{cat}/page/{page}/"
            )
            try:
                html = client.get(url).text
            except httpx.HTTPError:
                break
            links = {
                m
                for m in re.findall(rf"https://buyback\.nl/telefoon/{cat}/([a-z0-9][a-z0-9-]*)", html)
                if m != "page"
            }
            if not links - found and page > 1:
                break
            found |= links
            time.sleep(REQUEST_DELAY_SECONDS)
        out[brand] = sorted(found)
        logger.info("%s: discovered %d models", cat, len(found))
    return out


def parse_storage_gb(label: str) -> int | None:
    """Delegates to the sync script's parser so import and sync can never
    disagree about what a storage label means - a mismatch there silently
    produces devices the price sync can't find (see the 1TB/"1024GB" bug
    that this replaced)."""
    return storage_gb_from_label(label)


def model_name_from_html(html: str, slug: str) -> str | None:
    m = _H1_RE.search(html)
    if not m:
        return None
    name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    name = re.sub(r"\s+verkopen\??$", "", name, flags=re.IGNORECASE).strip()
    # Our `devices.brand` column already carries the brand, so the model
    # column stores "Galaxy S25 Ultra", not "Samsung Galaxy S25 Ultra".
    name = re.sub(r"^Samsung\s+", "", name).strip()
    return name or None


def our_slug(brand: Brand, model: str, storage_gb: int) -> str:
    # "+" must become "plus" before non-alphanumerics are stripped, or
    # "Galaxy S20+" and "Galaxy S20" collide on the unique slug index.
    normalized = model.lower().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", "-", f"{normalized} {storage_gb}gb").strip("-")


def main() -> None:
    created = updated = skipped_old = skipped_unknown = failed = 0
    slug_map: dict[str, str] = {}

    with Session(engine) as session, httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True
    ) as client:
        discovered = discover_slugs(client)

        for brand, slugs in discovered.items():
            for bb_slug in slugs:
                year = RELEASE_YEAR.get(bb_slug)
                if year is None:
                    logger.warning("%s: no release year mapped, skipping", bb_slug)
                    skipped_unknown += 1
                    continue
                if year < MIN_RELEASE_YEAR:
                    skipped_old += 1
                    continue

                cat = "iphone" if brand == Brand.apple else "samsung-galaxy"
                page_url = f"https://buyback.nl/telefoon/{cat}/{bb_slug}"
                try:
                    resp = client.get(page_url)
                    resp.raise_for_status()
                    html = resp.text
                except httpx.HTTPError as e:
                    logger.warning("%s: fetch failed (%s)", bb_slug, e)
                    failed += 1
                    continue
                time.sleep(REQUEST_DELAY_SECONDS)

                model = model_name_from_html(html, bb_slug)
                if not model:
                    logger.warning("%s: could not read model name", bb_slug)
                    failed += 1
                    continue

                storages = []
                for _, _, label in (
                    (m["field_id"], m["option_id"], m["label"]) for m in _OPTION_RE.finditer(html)
                ):
                    gb = parse_storage_gb(label)
                    if gb and gb not in storages:
                        storages.append(gb)
                if not storages:
                    logger.warning("%s: no storage options found", bb_slug)
                    failed += 1
                    continue

                has_s_pen = any(p.match(bb_slug) for p in S_PEN_PATTERNS)
                slug_map[f"{brand.value}|{model}"] = bb_slug

                for gb in storages:
                    existing = session.exec(
                        select(Device).where(
                            Device.brand == brand,
                            Device.model == model,
                            Device.storage_gb == gb,
                        )
                    ).first()
                    if existing:
                        existing.has_s_pen = has_s_pen
                        existing.is_active = True
                        session.add(existing)
                        updated += 1
                    else:
                        session.add(
                            Device(
                                brand=brand,
                                model=model,
                                storage_gb=gb,
                                color=None,
                                category=DeviceCategory.phone,
                                has_s_pen=has_s_pen,
                                slug=our_slug(brand, model, gb),
                                is_active=True,
                            )
                        )
                        created += 1

                logger.info(
                    "%s -> %s %s (%s) %s",
                    bb_slug,
                    brand.value,
                    model,
                    "/".join(f"{g}GB" for g in storages),
                    "[S-Pen]" if has_s_pen else "",
                )

        session.commit()

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    (SEED_DIR / "buyback_slugs.json").write_text(
        json.dumps(slug_map, indent=2, sort_keys=True) + "\n"
    )

    logger.info(
        "Done: %d created, %d updated, %d skipped (older than %d yrs), "
        "%d skipped (unmapped year), %d failed. Slug map: %d models.",
        created, updated, skipped_old, MAX_AGE_YEARS, skipped_unknown, failed, len(slug_map),
    )


if __name__ == "__main__":
    main()
