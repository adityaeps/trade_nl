"""Tests for the model-name -> release year guess used to sort the catalog.

The cases that matter are the ones where a plausible-looking pattern gives
the wrong answer: those are what put a phone in the wrong place in the
storefront, and they're invisible until someone eyeballs the order.
"""

import json
import pathlib

import pytest

from app.services.release_year import release_year_for


@pytest.mark.parametrize(
    "model,expected",
    [
        # Apple: one numbered model per year from the 12 (2020).
        ("iPhone 12", 2020),
        ("iPhone 12 Pro Max", 2020),
        ("iPhone 15", 2023),
        ("iPhone 17 Pro", 2025),
        # Samsung S: the number is the year.
        ("Galaxy S20", 2020),
        ("Galaxy S24 Ultra", 2024),
        ("Galaxy S26+", 2026),
        # Z Flip/Fold: generation + 2018.
        ("Galaxy Z Fold 4", 2022),
        ("Galaxy Z Flip7", 2025),
        # A-series: the second digit tracks the year.
        ("Galaxy A52", 2021),
        ("Galaxy A35", 2024),
        # Note: mapped, the numbering doesn't follow a rule.
        ("Galaxy Note20 Ultra", 2020),
    ],
)
def test_patterns(model, expected):
    assert release_year_for(model) == expected


@pytest.mark.parametrize(
    "model,expected",
    [
        # Every one of these is a case where the obvious pattern is WRONG.
        # They were caught by diffing against the importer's real launch
        # dates; without the explicit entries they'd each sit a year out.
        ("iPhone 16e", 2025),  # pattern says 2024 (shipped after the 16)
        ("Galaxy A12", 2020),  # pattern says 2021
        ("Galaxy A42 5G", 2020),  # pattern says 2021
        ("Galaxy S21 FE 5G", 2022),  # pattern says 2021 (FE shipped late)
        ("iPhone Air", 2025),  # no number at all
        ("Galaxy Z Flip", 2020),  # first gen, no digit
        ("Galaxy S10 Lite", 2020),  # Lite trails the base model
    ],
)
def test_models_the_patterns_get_wrong(model, expected):
    assert release_year_for(model) == expected


@pytest.mark.parametrize(
    "model,expected",
    [
        ("iPhone SE 2 (2020)", 2020),
        ("iPhone SE 3 (2022)", 2022),
        ("iPhone SE (3rd generation)", 2022),  # same phone, different spelling
    ],
)
def test_se_spellings_agree(model, expected):
    assert release_year_for(model) == expected


@pytest.mark.parametrize("model", ["", "   ", "Nokia 3310", "Pixel 9", "???"])
def test_unknown_returns_none_rather_than_guessing(model):
    # None sorts last in the catalog. Inventing a year would silently put an
    # unrecognised phone in the middle of the list.
    assert release_year_for(model) is None


def test_agrees_with_the_importers_real_launch_dates():
    """The importer's RELEASE_YEAR map is actual launch dates; this function
    is the fallback. They must not disagree, or a device's position depends
    on which code path created it."""
    from scripts.import_catalog_from_buyback import RELEASE_YEAR

    slug_map = pathlib.Path(__file__).resolve().parent.parent.parent / "seed-data" / "buyback_slugs.json"
    if not slug_map.exists():  # pragma: no cover - generated file
        pytest.skip("buyback_slugs.json not present")

    disagreements = []
    for key, slug in json.loads(slug_map.read_text()).items():
        model = key.partition("|")[2]
        authoritative = RELEASE_YEAR.get(slug)
        if authoritative is not None and release_year_for(model) != authoritative:
            disagreements.append((model, authoritative, release_year_for(model)))

    assert not disagreements, f"name-derived year disagrees with launch dates: {disagreements}"
