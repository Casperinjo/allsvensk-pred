"""Tests for api.main — the FastAPI endpoints.

The fetcher and the model are mocked, so these assert the HTTP contract (routing,
request/response shapes) without touching the network or loading a model.
"""

from fastapi.testclient import TestClient

import api.main as main

client = TestClient(main.app)


def test_upcoming_round_returns_predictions(monkeypatch):
    # The fetcher now returns dicts (id/date/time), and the endpoint zips those
    # onto each prediction — so the mock must supply them.
    monkeypatch.setattr(main, "fetch_upcoming_fixtures", lambda: [
        {"home": "A", "away": "B", "date": "2026-09-20", "time": "15:00:00", "id": "999"},
    ])
    monkeypatch.setattr(main, "predict_fixtures", lambda pairs: [
        {"home_team": "A", "away_team": "B", "home_win": 0.5, "draw": 0.3, "away_win": 0.2},
    ])

    resp = client.get("/upcoming-round")

    assert resp.status_code == 200
    preds = resp.json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["home_team"] == "A"
    assert preds[0]["home_win"] == 0.5
    # fixture metadata attached by the endpoint
    assert preds[0]["date"] == "2026-09-20"
    assert preds[0]["match_id"] == "999"


def test_predict_fixtures_accepts_body(monkeypatch):
    monkeypatch.setattr(main, "predict_fixtures", lambda pairs: [
        {"home_team": pairs[0][0], "away_team": pairs[0][1],
         "home_win": 0.4, "draw": 0.3, "away_win": 0.3},
    ])

    resp = client.post("/predict-fixtures", json={"fixtures": [{"home_team": "A", "away_team": "B"}]})

    assert resp.status_code == 200
    assert resp.json()["predictions"][0]["away_team"] == "B"

def test_index_page_is_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Allsvenskan" in resp.text  # the static frontend is mounted and reachable


def test_health_endpoint():
    # Cheap, dependency-free liveness/readiness check that deploy platforms poll.
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
