"""Postal-code geocoding (Nominatim) and haversine distance - see
ARCHITECTURE.md §4.

Unlike `pricing_engine.py`, this module is NOT pure: `geocode_postal_code`
makes an outbound HTTP call. `haversine_km` and `sort_stores_by_distance`
are pure and unit-tested.

Nominatim is a free, community-run service with a strict usage policy:
identify yourself with a real User-Agent, no more than 1 request/second,
and cache aggressively. Two things keep us inside that:

  * `@lru_cache` on the lookup - Dutch postal codes are stable and repeat
    heavily across customers, so in practice almost every request after
    the first for a given code is served from memory.
  * A module-level minimum interval between outbound calls.

The cache is per-process and resets on deploy. That's deliberate: §3 rules
out Redis for MVP, and a warm-up cost of one request per distinct postal
code is not worth adding infrastructure for. If store-locator traffic ever
justifies it, persist to a `postal_codes` table rather than reaching for a
cache server.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from functools import lru_cache

import httpx

logger = logging.getLogger("geocoding")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's policy requires a genuine identifying User-Agent with contact
# details - a generic or absent one gets blocked.
USER_AGENT = (
    "PhoneTradeInPlatform/1.0 "
    "(+https://github.com/adityaeps/trade_nl; store locator; contact: <business-email>)"
)
MIN_REQUEST_INTERVAL_SECONDS = 1.0
HTTP_TIMEOUT = 5.0

EARTH_RADIUS_KM = 6371.0

_rate_limit_lock = threading.Lock()
_last_request_at = 0.0


def _throttle() -> None:
    """Blocks so outbound calls stay >= 1s apart, per Nominatim's policy.

    Serialised across threads because uvicorn runs sync endpoints in a
    threadpool - without the lock, concurrent requests would each see a
    stale timestamp and fire simultaneously.
    """
    global _last_request_at
    with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic()


def normalize_postal_code(postal_code: str) -> str:
    """Dutch postal codes are '1012 JS' - 4 digits, optional space, 2
    letters. Normalised to uppercase with a single space so '1012js',
    '1012 js' and '1012JS' all share one cache entry."""
    cleaned = postal_code.strip().upper().replace(" ", "")
    if len(cleaned) == 6 and cleaned[:4].isdigit() and cleaned[4:].isalpha():
        return f"{cleaned[:4]} {cleaned[4:]}"
    return postal_code.strip().upper()


@lru_cache(maxsize=2048)
def geocode_postal_code(postal_code: str, country_code: str = "nl") -> tuple[float, float] | None:
    """Returns (lat, lng) for a postal code, or None if it can't be resolved.

    Returns None rather than raising: a failed lookup should degrade the
    store list to unsorted, not break the confirm page.

    NOTE: cached on the normalised postal code. Callers should pass the
    output of normalize_postal_code() so cache hits aren't missed on
    formatting differences alone.
    """
    _throttle()
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "postalcode": postal_code,
                "country": country_code,
                "format": "json",
                "limit": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Nominatim lookup failed for %r: %s", postal_code, e)
        return None

    if not results:
        logger.info("Nominatim had no match for %r", postal_code)
        return None

    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Nominatim returned an unparseable result for %r", postal_code)
        return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def sort_stores_by_distance(
    stores: list, origin: tuple[float, float] | None
) -> list[tuple[object, float | None]]:
    """Returns [(store, distance_km_or_None), ...].

    With no origin (unknown/omitted postal code) the original order is kept
    and every distance is None - the caller still gets a usable store list.
    Pure, so the ordering logic is unit-testable without touching Nominatim.
    """
    if origin is None:
        return [(store, None) for store in stores]
    lat, lng = origin
    scored = [(store, haversine_km(lat, lng, store.lat, store.lng)) for store in stores]
    scored.sort(key=lambda pair: pair[1])
    return scored
