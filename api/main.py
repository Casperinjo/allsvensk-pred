import logging
from pathlib import Path

from fastapi import Request
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from src.predict import predict_fixtures
from src.fixtures import fetch_upcoming_fixtures, fetch_recent_results
from src.store import save_predictions, load_predictions, score_predictions
from src.logging_config import setup_logging, request_id_var

import uuid


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Configure logging before anything else can emit a record. uvicorn imports this
# module after setting up its own loggers, so this call also gets to take those
# over (see setup_logging). Without it, Python's fallback handler drops anything
# below WARNING and writes unstructured text.
setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="Allsvenskan Predictor API")

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    raw = request.headers.get("X-Cloud-Trace-Context")
    rid = raw.split("/")[0][:64] if raw else uuid.uuid4().hex

    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    except Exception:
        # Still inside the ContextVar scope, so this line carries request_id —
        # which is the whole point: the 500 the user reports is greppable.
        logger.exception("Unhandled error")
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": rid},
        )
    finally:
        request_id_var.reset(token)

    response.headers["X-Request-ID"] = rid
    return response



class Fixture(BaseModel):
    home_team: str
    away_team: str


class FixturesRequest(BaseModel):
    fixtures: list[Fixture]


class Prediction(BaseModel):
    home_team: str
    away_team: str
    home_win: float
    draw: float
    away_win: float
    date: str | None = None
    time: str | None = None
    match_id : str | None = None



class PredictionsResponse(BaseModel):
    predictions: list[Prediction]

@app.get("/track-record")
def track_record_endpoint():
    try:
        score_predictions(fetch_recent_results())
    except Exception:
        logger.exception("Scoring on view failed")
    predictions = load_predictions()
    graded = [p for p in predictions if p["status"] != "pending"]
    correct = sum(1 for p in graded if p["status"] == "correct")
    accuracy = correct / len(graded) if graded else None

    record = {"total": len(predictions), "graded": len(graded),
             "correct": correct, "accuracy": accuracy,
             "predictions": predictions}
    return record

@app.post("/predict-fixtures", response_model=PredictionsResponse)
def predict_fixtures_endpoint(request: FixturesRequest) -> PredictionsResponse:
    pairs = [(f.home_team, f.away_team) for f in request.fixtures]
    results = predict_fixtures(pairs)
    return PredictionsResponse(predictions=results)



@app.get("/upcoming-round" , response_model=PredictionsResponse)
def get_upcoming_rounds_endpoint():
    upcoming_rounds = fetch_upcoming_fixtures()
    team_tuples = [(f["home"] , f["away"]) for f in upcoming_rounds]
    results = predict_fixtures(team_tuples)
    for pred, fixture in zip(results, upcoming_rounds):
        pred["date"] = fixture["date"]
        pred["time"] = fixture["time"]
        pred["match_id"] = fixture["id"]

    # Persistence is a side effect, not the endpoint's job — a Firestore outage
    # must not fail the prediction the user actually asked for. Log and move on.
    try:
        save_predictions(results)
    except Exception:
        logger.exception("Failed to save predictions to Firestore")

    return PredictionsResponse(predictions=results)

@app.get("/health")
def get_health():
    return {"status" : "ok"}

# Serve the frontend as static files. Mounted LAST so the API routes above (and
# FastAPI's own /docs, /openapi.json) take precedence; this "/" mount only catches
# what they didn't. html=True makes "/" serve index.html. Same origin as the API,
# so the page's fetch("/upcoming-round") needs no CORS.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


