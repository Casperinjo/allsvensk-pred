"""Firestore access for the results tracker.

Holds the cached Firestore client (connection boilerplate). The save/score logic
lives here too — written by you on top of `get_db()` and PREDICTIONS_COLLECTION.
"""

from google.cloud import firestore

# One Firestore collection holds all prediction records, one document per match
# (keyed by TheSportsDB match_id — see save logic).
PREDICTIONS_COLLECTION = "predictions"

_db = None


def get_db() -> firestore.Client:
    """Return a cached Firestore client.

    Auth is automatic: locally via Application Default Credentials
    (`gcloud auth application-default login`); on Cloud Run via the service
    account. Cached in module state so we open one client, not one per request
    (same pattern as predict.py's _load_artifacts).
    """
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


# --- Your save/score logic goes below ---
# save: given the /upcoming-round predictions (each carrying match_id, date, teams,
#   probs), write one document per match keyed by match_id, with status="pending".
#   Use get_db().collection(PREDICTIONS_COLLECTION).document(match_id).set({...}).

def save_predictions(predictions):
    db = get_db()
    collection = db.collection(PREDICTIONS_COLLECTION)
    for pred in predictions:
        match_id = pred["match_id"]
        doc_ref = collection.document(match_id)
        if doc_ref.get().exists:
            continue
        doc_ref.set({
            "match_id": match_id,
            "home_team": pred["home_team"],
            "away_team": pred["away_team"],
            "date": pred["date"],
            "home_win": pred["home_win"],
            "draw": pred["draw"],
            "away_win": pred["away_win"],
            "predicted_pick": pred["predicted_pick"],
            "status": "pending",
            "actual_result": None,
        })



