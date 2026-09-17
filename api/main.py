from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.predict import predict_fixtures
from src.fixtures import fetch_upcoming_fixtures

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Allsvenskan Predictor API")


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
    return PredictionsResponse(predictions=results)

@app.get("/health")
def get_health():
    return {"status" : "ok"}

# Serve the frontend as static files. Mounted LAST so the API routes above (and
# FastAPI's own /docs, /openapi.json) take precedence; this "/" mount only catches
# what they didn't. html=True makes "/" serve index.html. Same origin as the API,
# so the page's fetch("/upcoming-round") needs no CORS.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


