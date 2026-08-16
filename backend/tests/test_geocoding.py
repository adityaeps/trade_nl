"""Tests for the pure half of app/services/geocoding.py.

`geocode_postal_code` hits Nominatim and is deliberately not tested here -
these cover the distance maths and ordering, which is where a silent bug
would actually mis-rank stores for customers.
"""

import pytest

from app.services.geocoding import (
    haversine_km,
    normalize_postal_code,
    sort_stores_by_distance,
)


class FakeStore:
    def __init__(self, name: str, lat: float, lng: float):
        self.name = name
        self.lat = lat
        self.lng = lng

    def __repr__(self) -> str:
        return f"FakeStore({self.name})"


AMSTERDAM = (52.3731, 4.8926)
ROTTERDAM = (51.9244, 4.4777)
UTRECHT = (52.0907, 5.1214)


def test_haversine_known_distance_amsterdam_rotterdam():
    # Real-world great-circle distance is ~57.5 km; allow 1 km slack.
    assert haversine_km(*AMSTERDAM, *ROTTERDAM) == pytest.approx(57.5, abs=1.0)


def test_haversine_is_zero_for_same_point():
    assert haversine_km(*AMSTERDAM, *AMSTERDAM) == pytest.approx(0.0, abs=1e-9)


def test_haversine_is_symmetric():
    assert haversine_km(*AMSTERDAM, *UTRECHT) == pytest.approx(
        haversine_km(*UTRECHT, *AMSTERDAM)
    )


def test_sort_stores_orders_nearest_first():
    stores = [
        FakeStore("Rotterdam", *ROTTERDAM),
        FakeStore("Utrecht", *UTRECHT),
        FakeStore("Amsterdam", *AMSTERDAM),
    ]
    ranked = sort_stores_by_distance(stores, AMSTERDAM)

    assert [s.name for s, _ in ranked] == ["Amsterdam", "Utrecht", "Rotterdam"]
    assert ranked[0][1] == pytest.approx(0.0, abs=1e-9)
    # Distances must come back ascending, not just the stores.
    assert [d for _, d in ranked] == sorted(d for _, d in ranked)


def test_sort_stores_without_origin_preserves_order_and_nulls_distance():
    """An unresolvable postal code must not empty or reshuffle the picker."""
    stores = [FakeStore("B", *ROTTERDAM), FakeStore("A", *AMSTERDAM)]
    ranked = sort_stores_by_distance(stores, None)

    assert [s.name for s, _ in ranked] == ["B", "A"]
    assert all(distance is None for _, distance in ranked)


def test_sort_stores_handles_empty_list():
    assert sort_stores_by_distance([], AMSTERDAM) == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1012 JS", "1012 JS"),
        ("1012js", "1012 JS"),
        ("1012JS", "1012 JS"),
        ("  1012  js  ", "1012 JS"),
        ("3012 XJ", "3012 XJ"),
        ("nonsense", "NONSENSE"),  # passed through; Nominatim decides
    ],
)
def test_normalize_postal_code(raw, expected):
    assert normalize_postal_code(raw) == expected
