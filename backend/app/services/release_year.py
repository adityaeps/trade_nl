"""Derives an approximate release year from a device's model name.

The catalog has no release-date field and the importer (BuyBack.nl) doesn't
publish one, so "newest first" in the storefront needs a sortable key
derived from the only signal we have: the model name. This module is the
single place that guesses it.

Approximate is enough. The number is used only to order the catalog, never
shown to customers and never used in pricing - being a year out moves a
device a few rows, it doesn't misprice anything.

TODO(assumption): ARCHITECTURE.md doesn't specify a catalog sort order
beyond §8's plain device list. "Newest first, both brands" was requested by
the business 2026-08-16. If a real release date ever arrives (a supplier
feed, manual admin entry), store it on the device and sort by that instead -
this heuristic is a stand-in, not a fact.

Pure functions only: no DB, no HTTP. Backfilled into `devices.release_year`
by scripts/backfill_release_years.py and set on import for new devices.
"""

from __future__ import annotations

import re

# Families whose generation number maps onto a year by a fixed offset.
# Verified against the real catalog: iPhone 12 (2020) -> 17 (2025);
# Galaxy S20 (2020) -> S26 (2026); Z Flip/Fold 2 (2020) -> 7 (2025).
_IPHONE_NUMBERED = re.compile(r"^iphone\s+(\d+)", re.IGNORECASE)
_GALAXY_S = re.compile(r"^galaxy\s+s(\d{2})", re.IGNORECASE)
_GALAXY_A = re.compile(r"^galaxy\s+a(\d)(\d)", re.IGNORECASE)
_GALAXY_Z = re.compile(r"^galaxy\s+z\s*(?:flip|fold)\s*(\d+)", re.IGNORECASE)
_GALAXY_NOTE = re.compile(r"^galaxy\s+note\s*(\d+)", re.IGNORECASE)
_IPHONE_SE = re.compile(r"^iphone\s+se", re.IGNORECASE)
# "SE 2 (2020)", "SE 3 (2022)" carry the year outright; "(3rd generation)"
# gives the generation instead, so both spellings are handled below.
_YEAR_IN_NAME = re.compile(r"\((\d{4})\)")
_SE_GENERATION = re.compile(r"se\s*(?:\(?)(\d)(?:st|nd|rd|th)?", re.IGNORECASE)

# Models the patterns below get wrong, or can't parse at all.
#
# The authoritative source is RELEASE_YEAR in
# scripts/import_catalog_from_buyback.py (real launch dates, keyed by
# BuyBack.nl slug) - the importer uses that directly. This module is the
# fallback for callers that only have a model name, so the four models where
# the patterns disagreed with those launch dates are pinned here. Verified
# against the whole catalog: with these, name-derived == authoritative for
# all 92 known models.
_EXPLICIT: dict[str, int] = {
    "iphone air": 2025,  # Apple dropped the number entirely
    "galaxy z flip": 2020,  # first generation, no digit in the name
    "galaxy note10 lite": 2020,  # Lite shipped a year after the Note10
    "galaxy s10 lite": 2020,  # same pattern
    # --- pattern disagreed with the real launch date ---
    "iphone 16e": 2025,  # budget model, shipped a year after the iPhone 16
    "galaxy a12": 2020,  # A-series year digit breaks down on the A1x line
    "galaxy a42 5g": 2020,  # ditto
    "galaxy s21 fe 5g": 2022,  # FE shipped a year late
}

# Apple's numbered iPhones: iPhone 12 shipped 2020, and one per year since.
_IPHONE_YEAR_OFFSET = 2008
# Galaxy S: the number *is* the year (S20 -> 2020).
_GALAXY_S_CENTURY = 2000
# Galaxy A: the last digit tracks the year within a series (A52 -> 2021,
# A53 -> 2022, A13 -> 2022, A35 -> 2024).
_GALAXY_A_BASE = 2019
# Galaxy Z: Fold2/Flip2-era shipped 2020.
_GALAXY_Z_OFFSET = 2018
# Galaxy Note: Note10 -> 2019, Note20 -> 2020. Not a clean offset, so the
# two real cases are mapped directly.
_NOTE_YEARS = {10: 2019, 20: 2020}


def release_year_for(model: str) -> int | None:
    """Best guess at the year `model` was released, or None if unknown.

    Unknown is a legitimate answer - callers sort those last rather than
    inventing a position for them.
    """
    if not model:
        return None
    name = model.strip()
    lowered = name.lower()

    if lowered in _EXPLICIT:
        return _EXPLICIT[lowered]

    # A literal year in the name always wins: "iPhone SE 3 (2022)".
    explicit_year = _YEAR_IN_NAME.search(name)
    if explicit_year:
        year = int(explicit_year.group(1))
        if 2000 <= year <= 2100:
            return year

    if _IPHONE_SE.match(name):
        gen = _SE_GENERATION.search(name)
        if gen:
            # SE 1 (2016), SE 2 (2020), SE 3 (2022) - irregular spacing, so
            # map rather than compute.
            return {1: 2016, 2: 2020, 3: 2022}.get(int(gen.group(1)))
        return None

    iphone = _IPHONE_NUMBERED.match(name)
    if iphone:
        return _IPHONE_YEAR_OFFSET + int(iphone.group(1))

    galaxy_s = _GALAXY_S.match(name)
    if galaxy_s:
        return _GALAXY_S_CENTURY + int(galaxy_s.group(1))

    galaxy_z = _GALAXY_Z.match(name)
    if galaxy_z:
        return _GALAXY_Z_OFFSET + int(galaxy_z.group(1))

    note = _GALAXY_NOTE.match(name)
    if note:
        return _NOTE_YEARS.get(int(note.group(1)))

    galaxy_a = _GALAXY_A.match(name)
    if galaxy_a:
        # A<series><year-digit>: the second digit is the year marker.
        return _GALAXY_A_BASE + int(galaxy_a.group(2))

    return None
