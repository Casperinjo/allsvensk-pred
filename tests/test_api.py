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
    # Persistence is mocked out — the endpoint calls save_predictions, but the test
    # must not reach real Firestore (CI has no credentials). Capture what it's handed.
    saved = []
    monkeypatch.setattr(main, "save_predictions", lambda preds: saved.extend(preds))

    resp = client.get("/upcoming-round")

    assert resp.status_code == 200
    preds = resp.json()["predictions"]
    assert len(preds) == 1
    assert preds[0]["home_team"] == "A"
    assert preds[0]["home_win"] == 0.5
    # fixture metadata attached by the endpoint
    assert preds[0]["date"] == "2026-09-20"
    assert preds[0]["match_id"] == "999"
    # the predictions reached save_predictions WITH the fixture metadata attached
    assert len(saved) == 1
    assert saved[0]["match_id"] == "999"


def test_upcoming_round_survives_save_failure(monkeypatch):
    # A Firestore outage must not fail the prediction the user asked for: the
    # endpoint logs the error and still returns 200 with the predictions.
    monkeypatch.setattr(main, "fetch_upcoming_fixtures", lambda: [
        {"home": "A", "away": "B", "date": "2026-09-20", "time": "15:00:00", "id": "999"},
    ])
    monkeypatch.setattr(main, "predict_fixtures", lambda pairs: [
        {"home_team": "A", "away_team": "B", "home_win": 0.5, "draw": 0.3, "away_win": 0.2},
    ])

    def boom(preds):
        raise RuntimeError("Firestore is down")
    monkeypatch.setattr(main, "save_predictions", boom)

    resp = client.get("/upcoming-round")

    assert resp.status_code == 200
    assert resp.json()["predictions"][0]["home_team"] == "A"


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


# ---------------------------------------------------------------------------
# /track-record — scoring-on-view, then aggregation over stored predictions
# ---------------------------------------------------------------------------

def _stub_scoring(monkeypatch):
    """Neutralise the score-on-view side (network + Firestore) for these tests."""
    monkeypatch.setattr(main, "fetch_recent_results", lambda: [])
    monkeypatch.setattr(main, "score_predictions", lambda results: None)


def test_track_record_aggregates_graded(monkeypatch):
    _stub_scoring(monkeypatch)
    # 2 correct, 1 incorrect, 1 still pending -> accuracy is over the 3 graded only.
    monkeypatch.setattr(main, "load_predictions", lambda: [
        {"match_id": "1", "status": "correct", "predicted_pick": "home"},
        {"match_id": "2", "status": "correct", "predicted_pick": "away"},
        {"match_id": "3", "status": "incorrect", "predicted_pick": "home"},
        {"match_id": "4", "status": "pending", "predicted_pick": "draw"},
    ])

    resp = client.get("/track-record")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["graded"] == 3
    assert body["correct"] == 2
    assert body["accuracy"] == 2 / 3


def test_track_record_accuracy_none_when_nothing_graded(monkeypatch):
    # Divide-by-zero guard: before any match is played, accuracy must be null,
    # not a 500.
    _stub_scoring(monkeypatch)
    monkeypatch.setattr(main, "load_predictions", lambda: [
        {"match_id": "1", "status": "pending", "predicted_pick": "home"},
    ])

    resp = client.get("/track-record")

    assert resp.status_code == 200
    body = resp.json()
    assert body["graded"] == 0
    assert body["accuracy"] is None


def test_track_record_survives_scoring_failure(monkeypatch):
    # A failed score-on-view (network/Firestore down) must still return the
    # record from whatever is already stored.
    monkeypatch.setattr(main, "fetch_recent_results", lambda: (_ for _ in ()).throw(RuntimeError("API down")))
    monkeypatch.setattr(main, "load_predictions", lambda: [
        {"match_id": "1", "status": "correct", "predicted_pick": "home"},
    ])

    resp = client.get("/track-record")

    assert resp.status_code == 200
    assert resp.json()["correct"] == 1
