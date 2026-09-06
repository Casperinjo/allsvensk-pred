import json
from pathlib import Path

import joblib
import pandas as pd

from src.features import get_matchup_features, reshape_matches
from src.load import load_matches

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

_model = None
_scaler = None
_feature_columns = None


def _load_artifacts():
    """Load the persisted model/scaler/column-order once, cache in module state."""
    global _model, _scaler, _feature_columns
    if _model is None:
        _model = joblib.load(MODELS_DIR / "model.pkl")
        _scaler = joblib.load(MODELS_DIR / "scaler.pkl")
        with open(MODELS_DIR / "feature_columns.json") as f:
            _feature_columns = json.load(f)
    return _model, _scaler, _feature_columns


def predict_fixtures(fixtures: list[tuple[str, str]]) -> list[dict]:
    """fixtures: list of (home_team, away_team) pairs -> list of prediction dicts."""
    model, scaler, feature_columns = _load_artifacts()

    team_matches = reshape_matches(load_matches())
    rows = [get_matchup_features(home, away, team_matches) for home, away in fixtures]
    X = pd.DataFrame(rows, columns=feature_columns)
    X_scaled = scaler.transform(X)
    probs = model.predict_proba(X_scaled)

    # NOTE: encoding from src/load.py is 1=home win, 0=draw, 2=away win — NOT the
    # order you'd naively guess. model.classes_ tells us which probs column is which.
    class_index = {cls: i for i, cls in enumerate(model.classes_)}

    results = []
    for (home_team, away_team), p in zip(fixtures, probs):
        results.append({
            "home_team": home_team,
            "away_team": away_team,
            "home_win": float(p[class_index[1]]),
            "draw": float(p[class_index[0]]),
            "away_win": float(p[class_index[2]]),
        })
    return results
