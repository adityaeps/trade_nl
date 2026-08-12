"""Downloads a product image per device and points `devices.image_url` at it.

Images are written to `frontend/public/devices/<slug>.png`, which Next.js
serves from `/devices/<slug>.png` - on Vercel that's CDN-backed static
hosting at no extra cost, so no third-party image host/account is needed.
Swap SOURCE for a different provider (or drop files in by hand) without
touching anything else: the DB only ever stores the public path.

--- Image provenance / rights ---
SOURCE = "buyback" pulls the product image from BuyBack.nl's own page for
each model. Unlike the competitor *price* sync (facts - see
sync_competitor_prices.py's ToS review), product photography is a
copyrighted creative work owned by BuyBack.nl or the device manufacturer.
This script was run at the explicit direction of the business owner, who
confirmed they have the rights to use these assets. If that turns out not
to hold, this is fully reversible: delete frontend/public/devices/*, run
`python -m scripts.fetch_device_images --clear`, and the frontend falls
back to the built-in brand-logo placeholder tiles automatically.

Every downloaded file's origin is recorded in
frontend/public/devices/SOURCES.json so provenance stays auditable and
individual images can be swapped for owned/licensed replacements later.

Run:
    python -m scripts.fetch_device_images
    python -m scripts.fetch_device_images --clear   # unset image_url, keep files
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Device
from scripts.sync_competitor_prices import (
    BUYBACK_CATEGORY_SLUG,
    BUYBACK_SLUGS,
    REQUEST_DELAY_SECONDS,
    USER_AGENT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetch_device_images")

SOURCE = "buyback"

# frontend/public/devices/ - resolved relative to this file so it works from
# any cwd.
PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "devices"
PUBLIC_URL_PREFIX = "/devices"

_MODEL_IMG_RE = re.compile(r'https://buyback\.nl/media/images/model/[^"\'\s>]+\.png[^"\'\s>]*')


def buyback_image_url(client: httpx.Client, device: Device) -> str | None:
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
    except httpx.HTTPError as e:
        logger.warning("%s: page fetch failed (%s)", device.slug, e)
        return None

    match = _MODEL_IMG_RE.search(resp.text)
    if not match:
        logger.warning("%s: no model image found on %s", device.slug, page_url)
        return None
    return match.group(0)


def main() -> None:
    if "--clear" in sys.argv:
        with Session(engine) as session:
            devices = session.exec(select(Device)).all()
            for d in devices:
                d.image_url = None
                session.add(d)
            session.commit()
        logger.info("Cleared image_url on %d devices (files left on disk)", len(devices))
        return

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict[str, str]] = {}
    saved = 0

    with Session(engine) as session, httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True
    ) as client:
        devices = session.exec(select(Device)).all()
        logger.info("Fetching images for %d devices", len(devices))

        for device in devices:
            remote_url = buyback_image_url(client, device) if SOURCE == "buyback" else None
            time.sleep(REQUEST_DELAY_SECONDS)
            if not remote_url:
                continue

            try:
                img = client.get(remote_url)
                img.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("%s: image download failed (%s)", device.slug, e)
                continue

            if not img.content or len(img.content) < 512:
                logger.warning("%s: image looks empty/invalid, skipping", device.slug)
                continue

            dest = PUBLIC_DIR / f"{device.slug}.png"
            dest.write_bytes(img.content)

            device.image_url = f"{PUBLIC_URL_PREFIX}/{device.slug}.png"
            session.add(device)
            sources[device.slug] = {
                "source": SOURCE,
                "remote_url": remote_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "bytes": str(len(img.content)),
            }
            saved += 1
            logger.info("%s -> %s (%d bytes)", device.slug, device.image_url, len(img.content))
            time.sleep(REQUEST_DELAY_SECONDS)

        session.commit()

    if sources:
        manifest = PUBLIC_DIR / "SOURCES.json"
        existing = json.loads(manifest.read_text()) if manifest.exists() else {}
        existing.update(sources)
        manifest.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")

    logger.info("Saved %d images to %s", saved, PUBLIC_DIR)


if __name__ == "__main__":
    main()
