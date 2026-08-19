"""Integration tests for GET /stores.

Geocoding hits Nominatim over the network - never call it for real here.
`app.api.v1.stores` imports `geocode_postal_code` by name, so it's patched
on that module, matching how the endpoint actually resolves it.
"""

from tests.factories import make_store

AMSTERDAM = (52.3731, 4.8926)
ROTTERDAM = (51.9244, 4.4777)


def test_list_stores_without_postal_code_returns_null_distance(client, db_session):
    make_store(db_session, name="_pytest_B Store", lat=51.0, lng=4.0)
    make_store(db_session, name="_pytest_A Store", lat=52.0, lng=5.0)
    db_session.commit()

    resp = client.get("/api/v1/stores", params={"limit": 50})
    assert resp.status_code == 200
    rows = [r for r in resp.json() if r["name"].startswith("_pytest_")]
    assert all(r["distance_km"] is None for r in rows)
    names = [r["name"] for r in rows]
    assert names == sorted(names)  # name-ordered per the endpoint's fallback


def test_list_stores_with_postal_code_sorts_by_distance(client, db_session, monkeypatch):
    near = make_store(db_session, name="_pytest_Near", lat=AMSTERDAM[0], lng=AMSTERDAM[1])
    far = make_store(db_session, name="_pytest_Far", lat=ROTTERDAM[0], lng=ROTTERDAM[1])
    db_session.commit()

    monkeypatch.setattr("app.api.v1.stores.geocode_postal_code", lambda _postal: AMSTERDAM)

    resp = client.get("/api/v1/stores", params={"postal_code": "1012 JS", "limit": 50})
    assert resp.status_code == 200
    rows = [r for r in resp.json() if r["name"].startswith("_pytest_")]
    assert [r["name"] for r in rows] == ["_pytest_Near", "_pytest_Far"]
    assert rows[0]["distance_km"] == 0.0
    assert rows[1]["distance_km"] > rows[0]["distance_km"]


def test_list_stores_unresolvable_postal_code_degrades_gracefully(client, db_session, monkeypatch):
    make_store(db_session, name="_pytest_Only", lat=AMSTERDAM[0], lng=AMSTERDAM[1])
    db_session.commit()

    monkeypatch.setattr("app.api.v1.stores.geocode_postal_code", lambda _postal: None)

    resp = client.get("/api/v1/stores", params={"postal_code": "0000ZZ"})
    assert resp.status_code == 200
    assert any(r["name"] == "_pytest_Only" and r["distance_km"] is None for r in resp.json())


def test_list_stores_excludes_inactive(client, db_session):
    active = make_store(db_session, name="_pytest_Active", is_active=True)
    inactive = make_store(db_session, name="_pytest_Inactive", is_active=False)
    db_session.commit()

    resp = client.get("/api/v1/stores", params={"limit": 50})
    names = {r["name"] for r in resp.json()}
    assert active.name in names
    assert inactive.name not in names


def test_list_stores_limit(client, db_session):
    for i in range(5):
        make_store(db_session, name=f"_pytest_Limit{i}")
    db_session.commit()

    resp = client.get("/api/v1/stores", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2
