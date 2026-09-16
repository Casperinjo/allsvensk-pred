from fastapi import FastAPI
from pydantic import BaseModel

from src.predict import predict_fixtures
from src.fixtures import fetch_upcoming_fixtures

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


class PredictionsResponse(BaseModel):
    predictions: list[Prediction]


@app.post("/predict-fixtures", response_model=PredictionsResponse)
def predict_fixtures_endpoint(request: FixturesRequest) -> PredictionsResponse:
    pairs = [(f.home_team, f.away_team) for f in request.fixtures]
    results = predict_fixtures(pairs)
    return PredictionsResponse(predictions=results)

@app.get("/get-fixtures" , response_model=FixturesRequest)
def get_fixtures_endpoint() : 
    result = fetch_upcoming_fixtures()
    fixtures = []
    for home, away in result:
        fixture = Fixture(home_team=home, away_team=away)
        fixtures.append(fixture)
    return FixturesRequest(fixtures=fixtures)

@app.get("/upcoming-round" , response_model=PredictionsResponse)
def get_upcoming_rounds_endpoint():
    upcoming_rounds = fetch_upcoming_fixtures()
    results = predict_fixtures(upcoming_rounds)
    return PredictionsResponse(predictions=results)
