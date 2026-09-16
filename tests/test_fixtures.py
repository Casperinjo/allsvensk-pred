"""Tests for src.fixtures — TheSportsDB fetcher, name mapping, and caching.

All network calls are mocked; these tests never hit TheSportsDB.
"""

import pytest

import src.fixtures as fx
from src.fixtures import _map_team, NAME_MAP, fetch_upcoming_fixtures


class FakeResponse:
    """Stand-in for a requests.Response with just what the code touches."""
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def reset_module_cache():
    """The fetcher caches in module state; clear it around every test."""
    fx._cache = None
    fx._cache_time = None
    yield
    fx._cache = None
    fx._cache_time = None


# ---------------------------------------------------------------------------
# name mapping
# ---------------------------------------------------------------------------

def test_map_team_translates_known_names():
    assert _map_team("Malmö") == "Malmo FF"
    assert _map_team("IFK Göteborg") == "Goteborg"
    assert _map_team("AIK") == "AIK"  # identity entries still present


def test_map_team_raises_on_unknown():
    # Failing loud is the point — an unmapped team must NOT silently pass through
    # and get neutral (default) features.
    with pytest.raises(KeyError):
        _map_team("Some Unknown FC")


def test_name_map_covers_top_flight_and_has_valid_values():
    assert len(NAME_MAP) >= 16  # a full Allsvenskan season
    assert all(isinstance(v, str) and v for v in NAME_MAP.values())


# ---------------------------------------------------------------------------
# fetch_upcoming_fixtures
# ---------------------------------------------------------------------------

def test_fetch_keeps_only_not_started_and_maps_names(monkeypatch):
    payload = {"events": [
        {"strHomeTeam": "Malmö", "strAwayTeam": "AIK", "strStatus": "NS"},
        {"strHomeTeam": "Hammarby", "strAwayTeam": "GAIS", "strStatus": "FT"},  # played -> dropped
    ]}
    monkeypatch.setattr(fx.requests, "get", lambda *a, **k: FakeResponse(payload))

    result = fetch_upcoming_fixtures(days=1)

    assert result == [("Malmo FF", "AIK")]


def test_fetch_raises_on_unmapped_team(monkeypatch):
    payload = {"events": [
        {"strHomeTeam": "Unknown FC", "strAwayTeam": "AIK", "strStatus": "NS"},
    ]}
    monkeypatch.setattr(fx.requests, "get", lambda *a, **k: FakeResponse(payload))

    with pytest.raises(KeyError):
        fetch_upcoming_fixtures(days=1)


def test_fetch_serves_cached_result(monkeypatch):
    payload = {"events": [
        {"strHomeTeam": "Malmö", "strAwayTeam": "AIK", "strStatus": "NS"},
    ]}
    monkeypatch.setattr(fx.requests, "get", lambda *a, **k: FakeResponse(payload))
    first = fetch_upcoming_fixtures(days=1)

    # Swap the upstream data; a fresh call within the TTL must return the cache,
    # not the new (empty) data.
    monkeypatch.setattr(fx.requests, "get", lambda *a, **k: FakeResponse({"events": []}))
    second = fetch_upcoming_fixtures(days=1)

    assert second == first == [("Malmo FF", "AIK")]
