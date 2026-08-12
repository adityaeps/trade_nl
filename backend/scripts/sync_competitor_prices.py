"""Competitor price sync - see ARCHITECTURE.md §7.

Fetches a best-condition ("as new", fully functional) reference price per
device from Swappie.nl (Apple only) and BuyBack.nl (Apple + Samsung),
writes to `competitor_prices` (overwrite latest) and `price_history`
(append), then recomputes `base_prices.base_price` via
calculate_reference_price(). Connects directly to the database - not
routed through the FastAPI app (§7).

On a per-device failure (site unreachable, model not found, parsing
error), logs a warning and leaves that device's existing base_price
untouched rather than writing a bad value (§7) - one bad device never
blocks the rest of the run.

--- ToS / robots.txt review (2026-08-08, ahead of ARCHITECTURE.md §7's
automation gate) ---
Neither swappie.com's nor buyback.nl's Terms of Service contains a clause
prohibiting scraping, crawling, bots, or automated/programmatic access.
Neither site's robots.txt disallows the pages/endpoints this script hits
(both only disallow admin/cart/checkout/account paths and, for Swappie,
faceted filter URL combinations - not product or pricing pages/APIs).
Swappie's own frontend calls the public, unauthenticated JSON endpoint
used below - this script calls the exact same one. This is a point-in-time
review; both sites can change their ToS/robots.txt without notice, so
re-check periodically and stop immediately on a 403/429 pattern or any
change in these terms rather than working around it.

Etiquette: one request per device with a short delay between them
(REQUEST_DELAY_SECONDS), a descriptive User-Agent, and no concurrency -
this is a low-volume, low-frequency job (intended to run daily), not a
bulk crawl.

Run manually:

    python -m scripts.sync_competitor_prices

Scheduled via .github/workflows/sync-prices.yml.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Brand, Device
from app.models.pricing import BasePrice, CompetitorPrice, PriceHistory
from app.services.pricing_engine import calculate_reference_price

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_competitor_prices")

USER_AGENT = (
    "PhoneTradeInPlatformBot/1.0 "
    "(+https://github.com/<org>/phone-tradein-nl; competitor reference-price sync; "
    "contact: <business-email>)"
)
REQUEST_DELAY_SECONDS = 1.5
HTTP_TIMEOUT = 15.0

# Swappie.nl's pricing API sits behind Cloudflare bot protection - returns a
# JS challenge page to any plain HTTP client, confirmed 2026-08-08 across
# several realistic header combinations. fetch_swappie_price() below is
# implemented and correct (matches the real API response shape, confirmed
# via browser inspection) but cannot pass that challenge as-is. Decision
# (business, 2026-08-08): accept single-source reference prices from
# BuyBack.nl only for now rather than add headless-browser (Playwright)
# infra to CI - calculate_reference_price() already falls back to a single
# source cleanly (§6), same as it does for Samsung today. Flip this back on
# if/when Swappie access is solved (Playwright, an official feed, etc.).
SWAPPIE_ENABLED = False

# Swappie's own model naming doesn't always match ours 1:1 - extend this as
# mismatches are discovered. See ARCHITECTURE.md §11-style open assumption:
# this list is not exhaustive, only what's been confirmed so far.
SWAPPIE_MODEL_ALIASES = {
    "iPhone SE (3rd generation)": "iPhone SE 2022",
}

# Confirmed live 2026-08-08 against https://buyback.nl/telefoon/samsung-galaxy.
BUYBACK_CATEGORY_SLUG = {
    Brand.apple: "iphone",
    Brand.samsung: "samsung-galaxy",
}

# BuyBack.nl's per-model URL slug doesn't always follow a clean
# lowercase-hyphenate-the-model-name rule - Samsung models need a
# "samsung-" prefix BuyBack.nl's own iPhone slugs don't use, and hyphenation
# around trailing numbers is inconsistent even within Samsung's own slugs
# ("samsung-galaxy-s24" has no hyphen before "24", but
# "samsung-galaxy-z-flip-6" does before "6"). Confirmed live 2026-08-08 by
# reading https://buyback.nl/telefoon/{iphone,samsung-galaxy}(/page/N/)'s
# real links for every device currently in seed-data/devices.json - add an
# entry here for any new catalog device before relying on sync for it,
# rather than trusting the naive slugify fallback to guess right.
BUYBACK_SLUG_OVERRIDES: dict[tuple[Brand, str], str] = {
    (Brand.apple, "iPhone SE (3rd generation)"): "iphone-se-3-2022",
    (Brand.samsung, "Galaxy S25 Ultra"): "samsung-galaxy-s25-ultra",
    (Brand.samsung, "Galaxy S24"): "samsung-galaxy-s24",
    (Brand.samsung, "Galaxy A55"): "samsung-galaxy-a55",
    (Brand.samsung, "Galaxy Z Flip6"): "samsung-galaxy-z-flip-6",
}


def _load_generated_slug_map() -> dict[tuple[Brand, str], str]:
    """Merges in `seed-data/buyback_slugs.json`, written by
    import_catalog_from_buyback.py, so every imported model resolves to the
    slug it was actually discovered at instead of being re-derived (their
    naming is irregular). Hand-written OVERRIDES above still win, so a bad
    generated entry can always be corrected in code."""
    path = Path(__file__).resolve().parent.parent.parent / "seed-data" / "buyback_slugs.json"
    if not path.exists():
        return {}
    out: dict[tuple[Brand, str], str] = {}
    for key, slug in json.loads(path.read_text()).items():
        brand_value, _, model = key.partition("|")
        try:
            out[(Brand(brand_value), model)] = slug
        except ValueError:
            continue
    return out


BUYBACK_SLUGS: dict[tuple[Brand, str], str] = {
    **_load_generated_slug_map(),
    **BUYBACK_SLUG_OVERRIDES,
}

# BuyBack.nl's condition-question answer labels, preferred best-condition
# choice per question (in the order questions are actually asked - screen
# before housing, matching ARCHITECTURE.md §11's Samsung housing-question
# gap note; this list only needs entries that exist for the device's flow).
BUYBACK_BEST_ANSWERS = ["Ja", "Als nieuw"]


@dataclass
class CompetitorResult:
    competitor_name: str
    price: Decimal
    condition_tier: str
    source_url: str


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)


# --- Swappie.nl ------------------------------------------------------------


def fetch_swappie_price(client: httpx.Client, device: Device) -> CompetitorResult | None:
    if device.brand != Brand.apple:
        return None  # Swappie only lists Apple devices (§7).

    model = SWAPPIE_MODEL_ALIASES.get(device.model, device.model)
    storage_label = f"{device.storage_gb}GB"
    url = "https://swappie.com/api/sell/api/v3/prices/"
    params = {"model_name": model, "country": "NL", "storages": f'["{storage_label}"]'}

    try:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        entries = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Swappie: request failed for %s %s: %s", model, storage_label, e)
        return None

    target_name = f"{model} {storage_label}"
    for entry in entries:
        if (
            entry.get("model_name") == target_name
            and entry.get("visual_condition") == "ALMOST_NEW"
            and entry.get("functional_condition") == []
        ):
            price = entry.get("price", {}).get("price")
            if price is None or price <= 0:
                return None
            return CompetitorResult(
                competitor_name="swappie",
                price=Decimal(str(price)),
                condition_tier="ALMOST_NEW",
                source_url=f"{url}?model_name={model}",
            )

    logger.warning("Swappie: no best-condition entry found for %s", target_name)
    return None


# --- BuyBack.nl --------------------------------------------------------------

_OPTION_RE = re.compile(
    r'data-field-id="(?P<field_id>\d+)"\s+data-option-id="(?P<option_id>\d+)"[^>]*>\s*'
    r"<span>\s*(?P<label>[^<]+?)\s*</span>",
    re.IGNORECASE,
)
_MODEL_ID_RE = re.compile(r'id="current_model_id"[^>]*value="(\d+)"')
# First capacity-looking token in an option label. Deliberately takes the
# FIRST match so "128GB/8GB" (storage/RAM, common on mid-range Samsungs)
# resolves to the storage figure, not the RAM.
_CAPACITY_RE = re.compile(r"(\d+)\s*(TB|GB)\b", re.IGNORECASE)


def storage_gb_from_label(label: str) -> int | None:
    """Normalises any BuyBack.nl storage label to whole GB.

    Handles every spelling seen across the catalog - "64GB", "1TB",
    "1 TB", "128GB/8GB" - so callers compare integers instead of guessing
    at string formats. Returns None for labels that aren't capacities at
    all (some models ask "4G/5G" or "Single-SIM/Dual-SIM" first).
    """
    match = _CAPACITY_RE.search(label)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2).upper()
    return value * 1024 if unit == "TB" else value
_PRICE_RE = re.compile(r'class="variation-price">\s*([\d.,]+)\s*<')


def _parse_options(html: str) -> list[tuple[str, str, str]]:
    """Returns [(field_id, option_id, label), ...] parsed from a fragment
    of BuyBack.nl's option-button HTML (used for both the initial page and
    each AJAX step's field_options_html)."""
    return [(m["field_id"], m["option_id"], m["label"]) for m in _OPTION_RE.finditer(html)]


def _pick_best_option(options: list[tuple[str, str, str]]) -> tuple[str, str] | None:
    for preferred in BUYBACK_BEST_ANSWERS:
        for field_id, option_id, label in options:
            if label.strip().lower() == preferred.lower():
                return field_id, option_id
    if not options:
        return None
    # No recognized label (e.g. Samsung's battery question uses "Goed" /
    # "Normaal" / "Zwak", not iPhone's "Ja"/"Nee" - BUYBACK_BEST_ANSWERS
    # covers what's been seen live, not necessarily every question BuyBack.nl
    # has for every device category). Every question observed so far lists
    # its best-condition option first, so fall back to that rather than
    # failing the whole device - but log it, since this is a guess.
    field_id, option_id, label = options[0]
    logger.warning(
        "BuyBack.nl: no known-best label among %s, guessing first option %r",
        [o[2] for o in options],
        label,
    )
    return field_id, option_id


def fetch_buyback_price(client: httpx.Client, device: Device) -> CompetitorResult | None:
    category = BUYBACK_CATEGORY_SLUG.get(device.brand)
    if category is None:
        return None

    slug = BUYBACK_SLUGS.get(
        (device.brand, device.model),
        re.sub(r"[^a-z0-9]+", "-", device.model.lower()).strip("-"),
    )
    page_url = f"https://buyback.nl/telefoon/{category}/{slug}"

    try:
        resp = client.get(page_url)
        resp.raise_for_status()
        html = resp.text
    except httpx.HTTPError as e:
        logger.warning("BuyBack.nl: page fetch failed for %s: %s", page_url, e)
        return None

    model_id_match = _MODEL_ID_RE.search(html)
    if not model_id_match:
        logger.warning("BuyBack.nl: model_id not found on %s", page_url)
        return None
    model_id = model_id_match.group(1)

    # Match storage numerically rather than by label string. BuyBack.nl
    # spells the same capacity several ways across models ("512GB", "1TB",
    # "128GB/8GB" where the second figure is RAM), and every model has its
    # own set, so normalising both sides to GB is the only thing that holds
    # up across the whole catalog. See storage_gb_from_label().
    options = _parse_options(html)
    storage_option = next(
        (o for o in options if storage_gb_from_label(o[2]) == device.storage_gb), None
    )
    if not storage_option:
        logger.warning(
            "BuyBack.nl: no option matching %dGB for %s (offered: %s)",
            device.storage_gb,
            page_url,
            ", ".join(o[2].strip() for o in options) or "none",
        )
        return None

    field_id, option_id, _ = storage_option
    selected_attributes: dict[str, str] = {}

    # Walk the sequential wizard, choosing the best-condition answer at
    # each step, until the backend stops returning a new question.
    for _ in range(10):  # hard cap - real flow is ~5 steps, never open-ended
        selected_attributes[field_id] = option_id
        data = {
            "field_id": field_id,
            "option_id": option_id,
            "model_id": model_id,
            "link_base": "https://buyback.nl/",
            "site_lang": "dutch_netherlands",
            **{f"selected_attributes[{fid}]": oid for fid, oid in selected_attributes.items()},
        }
        try:
            resp = client.post(
                "https://buyback.nl/ajax/get_next_model_attr_v2.php", data=data
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("BuyBack.nl: wizard step failed for %s: %s", page_url, e)
            return None

        if payload.get("response_type") != "next_item":
            # Wizard finished: {"response_type": "last_item", "redirect_to":
            # "https://buyback.nl/offer", ...} - confirmed live 2026-08-08.
            # The offer page carries the price in
            # <span class="variation-price">222</span> inside an
            # h1.price_step_tree - session-scoped (cookies), not passed in
            # the URL, so it must be fetched with the same client/session.
            price = _extract_buyback_price(payload, client)
            if price is None:
                logger.warning(
                    "BuyBack.nl: could not extract final price for %s - "
                    "response shape may have changed, needs re-verification",
                    page_url,
                )
                return None
            if price <= 0:
                # Seen intermittently (not reproducible in isolation - looks
                # like transient session flakiness on BuyBack.nl's side, not
                # a parsing bug). A 0/negative price is never real, so treat
                # it the same as a failed fetch rather than ever writing it.
                logger.warning(
                    "BuyBack.nl: got a non-positive price (%s) for %s - "
                    "treating as a failed fetch",
                    price,
                    page_url,
                )
                return None
            return CompetitorResult(
                competitor_name="buyback",
                price=price,
                condition_tier="best (Als nieuw / Ja on every question)",
                source_url=page_url,
            )

        next_options = _parse_options(payload.get("field_options_html", ""))
        picked = _pick_best_option(next_options)
        if not picked:
            logger.warning(
                "BuyBack.nl: no recognized best-condition option on %s (field %s)",
                page_url,
                payload.get("field_id"),
            )
            return None
        field_id, option_id = picked

    logger.warning("BuyBack.nl: exceeded step limit for %s without a final price", page_url)
    return None


def _extract_buyback_price(payload: dict, client: httpx.Client) -> Decimal | None:
    """Extracts the price from the wizard's final response - confirmed live
    2026-08-08: {"response_type": "last_item", "redirect_to": "https://buyback.nl/offer"}.
    The offer page (same session/cookies) carries the price in
    <span class="variation-price">222</span>. Falls back to checking a few
    other plausible field names first, and to scanning any inline HTML the
    payload might carry directly, in case the site changes this shape -
    logs a clear warning (via the caller) rather than silently returning a
    stale/wrong price if none of these match."""
    for key in ("price", "estimate", "estimated_price"):
        if key in payload:
            try:
                return Decimal(str(payload[key]))
            except Exception:  # noqa: BLE001 - defensive, see docstring
                pass

    html_blob = payload.get("html") or payload.get("field_options_html") or ""
    match = _PRICE_RE.search(html_blob)
    if match:
        return Decimal(match.group(1).replace(".", "").replace(",", "."))

    redirect_url = payload.get("redirect_to") or payload.get("redirect_url") or payload.get("url")
    if redirect_url:
        try:
            resp = client.get(redirect_url)
            resp.raise_for_status()
            match = _PRICE_RE.search(resp.text)
            if match:
                return Decimal(match.group(1).replace(".", "").replace(",", "."))
        except httpx.HTTPError:
            pass

    return None


# --- Sync orchestration ------------------------------------------------------


def sync_device(session: Session, client: httpx.Client, device: Device) -> None:
    results: list[CompetitorResult] = []

    if SWAPPIE_ENABLED:
        swappie = fetch_swappie_price(client, device)
        if swappie:
            results.append(swappie)
        time.sleep(REQUEST_DELAY_SECONDS)

    buyback = fetch_buyback_price(client, device)
    if buyback:
        results.append(buyback)
    time.sleep(REQUEST_DELAY_SECONDS)

    if not results:
        logger.warning(
            "No competitor prices found for %s %s %sGB - leaving base_price untouched",
            device.brand,
            device.model,
            device.storage_gb,
        )
        return

    now = datetime.now(timezone.utc)
    for result in results:
        existing = session.exec(
            select(CompetitorPrice).where(
                CompetitorPrice.device_id == device.id,
                CompetitorPrice.competitor_name == result.competitor_name,
            )
        ).first()
        if existing:
            existing.price = result.price
            existing.condition_tier = result.condition_tier
            existing.source_url = result.source_url
            existing.checked_at = now
            session.add(existing)
        else:
            session.add(
                CompetitorPrice(
                    device_id=device.id,
                    competitor_name=result.competitor_name,
                    price=result.price,
                    condition_tier=result.condition_tier,
                    source_url=result.source_url,
                    checked_at=now,
                )
            )

    all_prices = session.exec(
        select(CompetitorPrice).where(CompetitorPrice.device_id == device.id)
    ).all()
    reference_price = calculate_reference_price(all_prices)

    session.add(PriceHistory(device_id=device.id, base_price=reference_price, recorded_at=now))

    base_price_row = session.exec(
        select(BasePrice).where(BasePrice.device_id == device.id)
    ).first()
    if base_price_row:
        base_price_row.base_price = reference_price
        base_price_row.last_synced_at = now
        session.add(base_price_row)
    else:
        # New device with no base_prices row yet - markup_pct is a business
        # decision (ARCHITECTURE.md §11), default to 0 and flag for review
        # rather than guessing a markup.
        logger.warning(
            "No base_prices row for %s %s %sGB - creating one with markup_pct=0, "
            "needs business review",
            device.brand,
            device.model,
            device.storage_gb,
        )
        from app.models.pricing import LiquidityTier

        session.add(
            BasePrice(
                device_id=device.id,
                base_price=reference_price,
                liquidity_tier=LiquidityTier.medium,
                markup_pct=Decimal("0"),
                last_synced_at=now,
            )
        )

    session.commit()
    logger.info(
        "%s %s %sGB: reference_price=%.2f from %s",
        device.brand,
        device.model,
        device.storage_gb,
        reference_price,
        ", ".join(r.competitor_name for r in results),
    )


def main() -> None:
    # --missing-only retries just the devices that still have no base_price.
    # Individual devices fail for transient reasons (timeouts, connection
    # resets, BuyBack.nl intermittently returning a 0 price), and re-scraping
    # the whole catalog to pick up a handful of stragglers is both slow and
    # needlessly heavy on their servers.
    missing_only = "--missing-only" in sys.argv

    with Session(engine) as session, _client() as client:
        query = select(Device).where(Device.is_active == True)  # noqa: E712
        devices = session.exec(query).all()
        if missing_only:
            priced = {
                bp.device_id for bp in session.exec(select(BasePrice)).all()
            }
            devices = [d for d in devices if d.id not in priced]
        logger.info(
            "Syncing competitor prices for %d devices%s",
            len(devices),
            " (missing-price only)" if missing_only else "",
        )
        for device in devices:
            sync_device(session, client, device)


if __name__ == "__main__":
    main()
